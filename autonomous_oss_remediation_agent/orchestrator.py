from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Callable

from .agent import AgentSession, default_agent_session_factory
from .capabilities import DeveloperCapabilitySet, ExecutionBudget, ProcessRunner, WorkspaceIO
from .capabilities.execution import BudgetExceeded
from .capabilities.policy import evaluate_runtime_boundary
from .config import RemediationRequest
from .deterministic.constraints import ConstraintEvaluator
from .deterministic.maven import MavenService
from .deterministic.osv import OsvScanner, ScannerPreflightError
from .deterministic.repository import RepositoryPreparationError, RepositoryPreparer
from .deterministic.validation import DeterministicValidator
from .integrations.delivery import DeliveryAdapter, DeliveryContext, ManualDeliveryAdapter
from .models import (
    DeliveryResult,
    Outcome,
    RepositoryBaseline,
    RunResult,
    ValidationReport,
)
from .prompt import initial_message, validation_feedback
from .workspace import RunWorkspace, TraceStore


AgentSessionFactory = Callable[[DeveloperCapabilitySet, str], AgentSession]
ScannerFactory = Callable[[RunWorkspace, ProcessRunner, TraceStore], OsvScanner]
DeliveryAdapterFactory = Callable[[RunWorkspace, ProcessRunner, TraceStore], DeliveryAdapter]


class AutonomousRemediationOrchestrator:
    def __init__(
        self,
        request: RemediationRequest,
        *,
        delivery_adapter: DeliveryAdapter | None = None,
        delivery_adapter_factory: DeliveryAdapterFactory | None = None,
        agent_session_factory: AgentSessionFactory = default_agent_session_factory,
        scanner_factory: ScannerFactory = OsvScanner,
    ):
        if delivery_adapter is not None and delivery_adapter_factory is not None:
            raise ValueError("Specify delivery_adapter or delivery_adapter_factory, not both")
        self.request = request
        self.delivery_adapter = delivery_adapter or ManualDeliveryAdapter()
        self.delivery_adapter_factory = delivery_adapter_factory
        self.agent_session_factory = agent_session_factory
        self.scanner_factory = scanner_factory

    def run(self) -> RunResult:
        return asyncio.run(self.run_async())

    async def run_async(self) -> RunResult:
        workspace = RunWorkspace.create(self.request.workspace_parent)
        trace = TraceStore(workspace)
        trace.write_json("request.json", self.request.to_dict())
        budget = ExecutionBudget(self.request.budget)
        process_runner = ProcessRunner(workspace, trace, budget, self.request.runtime_policy)
        delivery_adapter = (
            self.delivery_adapter_factory(workspace, process_runner, trace)
            if self.delivery_adapter_factory
            else self.delivery_adapter
        )
        boundary = evaluate_runtime_boundary(self.request.runtime_policy)
        trace.write_json("runtime-boundary.json", boundary.__dict__)
        if not boundary.approved:
            return self._finish(
                trace,
                RunResult(
                    Outcome.BASELINE_FAILURE,
                    f"RUNTIME_BOUNDARY_NOT_APPROVED: {boundary.reason}",
                    str(workspace.root),
                ),
            )
        delivery_preflight = delivery_adapter.preflight(self.request)
        trace.write_json("delivery/preflight.json", delivery_preflight.to_dict())
        scanner = self.scanner_factory(workspace, process_runner, trace)
        try:
            scanner.preflight(self.request.scanner)
            metadata = RepositoryPreparer(workspace, process_runner, trace).clone(
                self.request.repository_url,
                self.request.reference_branch,
            )
            maven = MavenService(workspace.repository, process_runner)
            build_results = maven.run_baseline(
                self.request.build_commands,
                self.request.test_commands,
                self.request.startup_commands,
            )
            if not build_results or not all(result.succeeded for result in build_results):
                raise RuntimeError("Baseline Maven build failed")
            scan = scanner.scan(workspace.repository, self._baseline_scan_scope(), "baseline")
            if not scan.succeeded:
                raise RuntimeError(f"Baseline OSV scan failed: {scan.error}")
            constraint_evaluator = ConstraintEvaluator()
            constraint_baseline = constraint_evaluator.capture(workspace.repository)
            targets = tuple(finding for finding in scan.findings if self._is_target(finding))
            baseline = RepositoryBaseline(
                repository_path=metadata.path,
                commit=metadata.commit,
                reference=metadata.reference,
                remote_url=metadata.remote_url,
                build_results=build_results,
                scan=scan,
                constraints=constraint_baseline,
                target_findings=targets,
            )
            trace.write_json("baseline/baseline.json", baseline.to_dict())
        except (ScannerPreflightError, RepositoryPreparationError, RuntimeError, BudgetExceeded) as exc:
            return self._finish(
                trace,
                RunResult(
                    Outcome.BASELINE_FAILURE,
                    str(exc),
                    str(workspace.root),
                ),
            )

        workspace_io = WorkspaceIO(workspace, trace)
        capabilities = DeveloperCapabilitySet(workspace_io, process_runner, budget, trace)
        agent_session = self.agent_session_factory(capabilities, self.request.model)
        validator = DeterministicValidator(
            self.request,
            workspace,
            process_runner,
            scanner,
            constraint_evaluator,
            trace,
        )
        message = initial_message(self.request, baseline)
        summaries: list[str] = []
        last_validation: ValidationReport | None = None
        agent_closed = False
        try:
            for cycle in range(1, self.request.budget.max_cycles + 1):
                budget.ensure_time_remaining()
                turn = await agent_session.run_turn(message)
                summaries.append(turn.text)
                trace.write_json(f"agent/cycle-{cycle}.json", {"summary": turn.text})
                last_validation = validator.validate(cycle, baseline)
                if last_validation.passed:
                    await agent_session.close()
                    agent_closed = True
                    delivery = self._deliver(
                        delivery_adapter,
                        delivery_preflight.eligible,
                        workspace,
                        baseline,
                        last_validation,
                        summaries[-1] if summaries else "",
                    )
                    outcome = Outcome.SUCCESS if delivery.succeeded else Outcome.PARTIAL_MANUAL_REVIEW_REQUIRED
                    reason = "Validated remediation delivered as a Draft PR" if delivery.succeeded else (delivery.reason or delivery.status)
                    return self._finish(
                        trace,
                        RunResult(
                            outcome,
                            reason,
                            str(workspace.root),
                            baseline=baseline,
                            validation=last_validation,
                            delivery=delivery,
                            cycles_completed=cycle,
                            agent_summaries=tuple(summaries),
                        ),
                    )
                if turn.text.strip().upper().startswith("NO_SAFE_REMEDIATION:"):
                    return self._finish(
                        trace,
                        RunResult(
                            Outcome.NO_SAFE_REMEDIATION,
                            turn.text.strip(),
                            str(workspace.root),
                            baseline=baseline,
                            validation=last_validation,
                            cycles_completed=cycle,
                            agent_summaries=tuple(summaries),
                        ),
                    )
                if budget.tool_calls >= self.request.budget.max_tool_calls or budget.remaining_seconds <= 0:
                    break
                message = validation_feedback(last_validation)
        except BudgetExceeded as exc:
            reason = str(exc)
        except Exception as exc:
            return self._finish(
                trace,
                RunResult(
                    Outcome.PARTIAL_MANUAL_REVIEW_REQUIRED,
                    f"AGENT_RUNTIME_FAILURE: {exc}",
                    str(workspace.root),
                    baseline=baseline,
                    validation=last_validation,
                    cycles_completed=len(summaries),
                    agent_summaries=tuple(summaries),
                ),
            )
        else:
            reason = "Configured remediation/validation cycle limit reached"
        finally:
            if not agent_closed:
                try:
                    await agent_session.close()
                except Exception:
                    pass
        return self._finish(
            trace,
            RunResult(
                Outcome.EXECUTION_LIMIT_REACHED,
                reason,
                str(workspace.root),
                baseline=baseline,
                validation=last_validation,
                cycles_completed=len(summaries),
                agent_summaries=tuple(summaries),
            ),
        )

    def _deliver(
        self,
        delivery_adapter: DeliveryAdapter,
        preflight_eligible: bool,
        workspace: RunWorkspace,
        baseline: RepositoryBaseline,
        validation: ValidationReport,
        agent_summary: str,
    ) -> DeliveryResult:
        if not preflight_eligible or not validation.delivery_eligible:
            return DeliveryResult(
                False,
                "VALIDATED_MANUAL_DELIVERY_REQUIRED",
                reason="Validation passed but isolated automated delivery is unavailable or ineligible",
                evidence={"diffPath": validation.diff_path, "treeDigest": validation.tree_digest},
            )
        return delivery_adapter.deliver(
            DeliveryContext(
                request=self.request,
                workspace=workspace,
                baseline=baseline,
                validation=validation,
                agent_summary=agent_summary,
            )
        )

    def _baseline_scan_scope(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.request.severity_scope) | set(self.request.constraints.prohibited_new_severities)))

    def _is_target(self, finding) -> bool:
        if finding.severity not in set(self.request.severity_scope):
            return False
        requested_ids = {value.upper() for value in self.request.vulnerability_ids}
        return not requested_ids or bool(requested_ids & finding.identifiers)

    @staticmethod
    def _finish(trace: TraceStore, result: RunResult) -> RunResult:
        trace.write_json("final-result.json", result.to_dict())
        trace.append_event("run_finished", outcome=result.outcome.value, reason=result.reason)
        return result
