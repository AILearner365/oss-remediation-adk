from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Callable

from .agent import AgentSession, default_agent_session_factory
from .capabilities import DeveloperCapabilitySet, ExecutionBudget, ProcessRunner, WorkspaceIO
from .capabilities.execution import BudgetExceeded
from .capabilities.decisions import DecisionTracker
from .capabilities.policy import evaluate_runtime_boundary
from .config import RemediationRequest, ScannerConfig
from .deterministic.constraints import ConstraintEvaluator
from .deterministic.maven import MavenService
from .deterministic.repository import RepositoryPreparationError, RepositoryPreparer
from .deterministic.scanner import ScannerPreflightError, VulnerabilityScanner, create_scanner
from .deterministic.validation import DeterministicValidator
from .integrations.delivery import DeliveryAdapter, DeliveryContext, ManualDeliveryAdapter
from .models import (
    AgentDecisionStatus,
    DecisionCaptureAssessment,
    DecisionCaptureStatus,
    DeliveryResult,
    DeterministicValidationStatus,
    DecisionState,
    EffectiveResolutionStatus,
    FinalDecisionState,
    Outcome,
    RepositoryBaseline,
    RunResult,
    ScanFailureKind,
    ScanReport,
    ValidationReport,
)
from .prompt import (
    decision_reconciliation_message,
    extract_working_state,
    initial_message,
    validation_feedback,
)
from .workspace import RunWorkspace, TraceStore


AgentSessionFactory = Callable[[DeveloperCapabilitySet, str], AgentSession]
ScannerFactory = Callable[[ScannerConfig, RunWorkspace, ProcessRunner, TraceStore], VulnerabilityScanner]
DeliveryAdapterFactory = Callable[[RunWorkspace, ProcessRunner, TraceStore], DeliveryAdapter]


_SCANNER_INFRASTRUCTURE_FAILURES = frozenset(
    {
        ScanFailureKind.AUTHENTICATION,
        ScanFailureKind.AUTHORIZATION,
        ScanFailureKind.NETWORK,
        ScanFailureKind.TIMEOUT,
        ScanFailureKind.CONFIGURATION,
        ScanFailureKind.INVALID_RESPONSE,
        ScanFailureKind.BACKEND,
    }
)


class AutonomousRemediationOrchestrator:
    def __init__(
        self,
        request: RemediationRequest,
        *,
        delivery_adapter: DeliveryAdapter | None = None,
        delivery_adapter_factory: DeliveryAdapterFactory | None = None,
        agent_session_factory: AgentSessionFactory = default_agent_session_factory,
        scanner_factory: ScannerFactory = create_scanner,
    ):
        if delivery_adapter is not None and delivery_adapter_factory is not None:
            raise ValueError("Specify delivery_adapter or delivery_adapter_factory, not both")
        self.request = request
        self.delivery_adapter = delivery_adapter or ManualDeliveryAdapter()
        self.delivery_adapter_factory = delivery_adapter_factory
        self.agent_session_factory = agent_session_factory
        self.scanner_factory = scanner_factory
        self._decision_tracker: DecisionTracker | None = None

    def run(self) -> RunResult:
        return asyncio.run(self.run_async())

    async def run_async(self) -> RunResult:
        self._decision_tracker = None
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
        scanner = (
            create_scanner(
                self.request.scanner,
                workspace,
                process_runner,
                trace,
                maven_config=self.request.maven,
            )
            if self.scanner_factory is create_scanner
            else self.scanner_factory(self.request.scanner, workspace, process_runner, trace)
        )
        try:
            scanner.preflight(self.request.scanner)
            metadata = RepositoryPreparer(workspace, process_runner, trace).clone(
                self.request.repository_url,
                self.request.reference_branch,
            )
            maven = MavenService(workspace.repository, process_runner, self.request.maven)
            build_results = maven.run_baseline(
                self.request.build_commands,
                self.request.test_commands,
                self.request.startup_commands,
            )
            if not build_results or not all(result.succeeded for result in build_results):
                raise RuntimeError("Baseline Maven build failed")
            scan = scanner.scan(workspace.repository, self._baseline_scan_scope(), "baseline")
            if not scan.succeeded:
                raise RuntimeError(
                    f"Baseline vulnerability scan failed ({scan.effective_outcome.value}): {scan.error}"
                )
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

        if self.request.vulnerability_ids and not baseline.target_findings:
            requested_ids = ", ".join(self.request.vulnerability_ids)
            return self._finish(
                trace,
                RunResult(
                    Outcome.REQUESTED_VULNERABILITY_NOT_FOUND,
                    "REQUESTED_VULNERABILITY_NOT_FOUND: None of the requested vulnerability IDs "
                    f"were found in the completed baseline scan: {requested_ids}",
                    str(workspace.root),
                    baseline=baseline,
                ),
            )

        workspace_io = WorkspaceIO(workspace, trace)
        capabilities = DeveloperCapabilitySet(workspace_io, process_runner, budget, trace)
        self._decision_tracker = capabilities.decisions
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
                capabilities.start_cycle(cycle)
                validator.capture_cycle_start(cycle, baseline)
                turn = await agent_session.run_turn(message)
                summaries.append(turn.text)
                working_state = extract_working_state(turn.text)
                reconciliation = await self._reconcile_decision_capture(
                    cycle,
                    turn.text,
                    working_state,
                    baseline,
                    validator,
                    capabilities,
                    agent_session,
                    trace,
                )
                decision_state = capabilities.decisions.current_state
                decision_trail = capabilities.decisions.records_for_cycle(cycle)
                capture_assessment = capabilities.decisions.capture_assessment
                cycle_artifact: dict[str, object] = {
                    "summary": turn.text,
                    "workingState": working_state,
                    "decisionCaptureStatus": capture_assessment.status.value,
                    "decisionCapture": capture_assessment.to_dict(),
                }
                if reconciliation is not None:
                    cycle_artifact["decisionReconciliation"] = reconciliation
                if decision_state is not None:
                    cycle_artifact["decisionState"] = decision_state.to_dict()
                    cycle_artifact["decisionTrail"] = [
                        decision.to_dict() for decision in decision_trail
                    ]
                trace.write_json(
                    f"agent/cycle-{cycle}.json",
                    cycle_artifact,
                )
                if not decision_trail:
                    capabilities.decisions.warn(
                        cycle,
                        "No material decision was recorded during the agent cycle",
                    )
                if capture_assessment.status != DecisionCaptureStatus.COMPLETE:
                    capabilities.decisions.warn(
                        cycle,
                        "Decision capture remains deficient after reconciliation",
                        decisionCaptureStatus=capture_assessment.status.value,
                        reasons=list(capture_assessment.reasons),
                    )
                last_validation = validator.validate(cycle, baseline)
                if (
                    decision_state is not None
                    and decision_state.agent_status == AgentDecisionStatus.READY
                    and not last_validation.passed
                ):
                    capabilities.decisions.warn(
                        cycle,
                        "Agent readiness decision contradicted deterministic validation",
                        decisionId=decision_state.latest_decision_id,
                    )
                elif last_validation.passed and (
                    decision_state is None
                    or decision_state.agent_status != AgentDecisionStatus.READY
                ):
                    capabilities.decisions.warn(
                        cycle,
                        "Deterministic validation passed without a current readiness decision",
                    )
                if _is_scanner_infrastructure_failure(last_validation.scan):
                    await agent_session.close()
                    agent_closed = True
                    scan = last_validation.scan
                    return self._finish(
                        trace,
                        RunResult(
                            Outcome.PARTIAL_MANUAL_REVIEW_REQUIRED,
                            "VALIDATION_SCANNER_FAILURE: "
                            f"{scan.effective_outcome.value}: {scan.error}",
                            str(workspace.root),
                            baseline=baseline,
                            validation=last_validation,
                            cycles_completed=cycle,
                            agent_summaries=tuple(summaries),
                        ),
                    )
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
                        capabilities.decisions.capture_assessment,
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
                capabilities.decisions.require_update_after_failed_validation(cycle)
                message = validation_feedback(
                    last_validation,
                    working_state,
                    capabilities.decisions.current_state,
                    capabilities.decisions.all_records(),
                )
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
        decision_capture: DecisionCaptureAssessment,
    ) -> DeliveryResult:
        if decision_capture.status != DecisionCaptureStatus.COMPLETE:
            return DeliveryResult(
                False,
                "VALIDATED_DECISION_AUDIT_REVIEW_REQUIRED",
                reason=(
                    "Deterministic validation passed, but automatic delivery was withheld "
                    "because decision capture is "
                    f"{decision_capture.status.value}"
                ),
                evidence={
                    "diffPath": validation.diff_path,
                    "treeDigest": validation.tree_digest,
                    "decisionCapture": decision_capture.to_dict(),
                    "validationWarnings": list(validation.warnings),
                },
            )
        if not preflight_eligible or not validation.delivery_eligible:
            return DeliveryResult(
                False,
                "VALIDATED_MANUAL_DELIVERY_REQUIRED",
                reason=(
                    "; ".join(validation.warnings)
                    if validation.warnings
                    else "Validation passed but isolated automated delivery is unavailable or ineligible"
                ),
                evidence={
                    "diffPath": validation.diff_path,
                    "treeDigest": validation.tree_digest,
                    "validationWarnings": list(validation.warnings),
                    "diagnosticArtifacts": list(validation.diagnostic_artifacts),
                },
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

    async def _reconcile_decision_capture(
        self,
        cycle: int,
        turn_text: str,
        working_state: str,
        baseline: RepositoryBaseline,
        validator: DeterministicValidator,
        capabilities: DeveloperCapabilitySet,
        agent_session: AgentSession,
        trace: TraceStore,
    ) -> dict[str, object] | None:
        assessment_before = capabilities.decisions.capture_assessment
        if assessment_before.status == DecisionCaptureStatus.COMPLETE:
            return None

        changed_files = validator.changed_files(baseline.commit)
        decision_count_before = capabilities.decisions.event_count
        operational_calls_before = capabilities.budget.tool_calls
        message = decision_reconciliation_message(
            assessment_before,
            working_state,
            turn_text,
            capabilities.decisions.current_state,
            capabilities.decisions.all_records(),
            changed_files,
            capabilities.decisions.workspace_edit_paths,
        )
        response_text = ""
        error = None
        try:
            with capabilities.decision_reconciliation_only():
                response = await agent_session.run_turn(message)
                response_text = response.text
        except Exception as exc:
            error = str(exc)
            capabilities.decisions.warn(
                cycle,
                "Decision-capture reconciliation turn failed",
                error=error,
            )

        assessment_after = capabilities.decisions.capture_assessment
        recorded_count = capabilities.decisions.event_count - decision_count_before
        operational_calls_consumed = (
            capabilities.budget.tool_calls - operational_calls_before
        )
        result: dict[str, object] = {
            "attempted": True,
            "statusBefore": assessment_before.status.value,
            "statusAfter": assessment_after.status.value,
            "reason": list(assessment_before.reasons),
            "recordedDecisionCount": recorded_count,
            "operationalToolCallsConsumed": operational_calls_consumed,
            "changedFiles": list(changed_files),
        }
        if response_text:
            normalized_response = " ".join(response_text.split())
            result["responseExcerpt"] = normalized_response[:1_200]
        if error:
            result["error"] = error
        trace.append_event(
            "decision_reconciliation",
            cycle=cycle,
            statusBefore=assessment_before.status.value,
            statusAfter=assessment_after.status.value,
            recordedDecisionCount=recorded_count,
            operationalToolCallsConsumed=operational_calls_consumed,
            error=error,
        )
        return result

    def _baseline_scan_scope(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.request.severity_scope) | set(self.request.constraints.prohibited_new_severities)))

    def _is_target(self, finding) -> bool:
        if finding.severity not in set(self.request.severity_scope):
            return False
        requested_ids = {value.upper() for value in self.request.vulnerability_ids}
        return not requested_ids or bool(requested_ids & finding.identifiers)

    def _finish(self, trace: TraceStore, result: RunResult) -> RunResult:
        if self._decision_tracker:
            decision_capture = self._decision_tracker.capture_assessment
            current_state = self._decision_tracker.current_state
            validation_status = _deterministic_validation_status(result.validation)
            effective_status = _effective_resolution_status(
                result,
                validation_status,
                current_state,
            )
            result = replace(
                result,
                decision_capture=decision_capture,
                deterministic_validation_status=validation_status,
                effective_resolution_status=effective_status,
            )
            if current_state is not None:
                final_decision_state = _resolve_final_decision_state(
                    result,
                    current_state,
                )
                result = replace(
                    result,
                    final_decision_state=final_decision_state,
                    decision_event_count=self._decision_tracker.event_count,
                )
        trace.write_json("final-result.json", result.to_dict())
        trace.append_event("run_finished", outcome=result.outcome.value, reason=result.reason)
        return result


def _is_scanner_infrastructure_failure(report: ScanReport | None) -> bool:
    return bool(
        report
        and not report.succeeded
        and report.failure_kind in _SCANNER_INFRASTRUCTURE_FAILURES
    )


def _resolve_final_decision_state(
    result: RunResult,
    agent_state: DecisionState,
) -> FinalDecisionState:
    validation_status = _deterministic_validation_status(result.validation)
    effective_status = _effective_resolution_status(
        result,
        validation_status,
        agent_state,
    )

    warnings = []
    if (
        agent_state.agent_status == AgentDecisionStatus.READY
        and validation_status != DeterministicValidationStatus.PASSED
    ):
        warnings.append("Agent readiness was not confirmed by deterministic validation")
    if (
        validation_status == DeterministicValidationStatus.PASSED
        and agent_state.agent_status != AgentDecisionStatus.READY
    ):
        warnings.append(
            "Deterministic validation passed despite the agent not recording readiness"
        )
    return FinalDecisionState(
        agent_decision_state=agent_state,
        deterministic_validation_status=validation_status,
        effective_resolution_status=effective_status,
        warnings=tuple(warnings),
    )


def _effective_resolution_status(
    result: RunResult,
    validation_status: DeterministicValidationStatus,
    agent_state: DecisionState | None,
) -> EffectiveResolutionStatus:
    if validation_status == DeterministicValidationStatus.PASSED:
        return EffectiveResolutionStatus.VALIDATED
    if validation_status == DeterministicValidationStatus.FAILED:
        if (
            result.outcome == Outcome.NO_SAFE_REMEDIATION
            and agent_state is not None
            and agent_state.agent_status == AgentDecisionStatus.BLOCKED
        ):
            return EffectiveResolutionStatus.BLOCKED
        return EffectiveResolutionStatus.VALIDATION_REJECTED
    return EffectiveResolutionStatus.INCOMPLETE


def _deterministic_validation_status(
    validation: ValidationReport | None,
) -> DeterministicValidationStatus:
    if validation is None:
        return DeterministicValidationStatus.NOT_RUN
    if validation.scan is not None and not validation.scan.succeeded:
        return DeterministicValidationStatus.INCOMPLETE
    if validation.passed:
        return DeterministicValidationStatus.PASSED
    return DeterministicValidationStatus.FAILED
