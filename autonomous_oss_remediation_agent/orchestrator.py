from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Callable

from .agent import AgentSession, default_agent_session_factory
from .capabilities import DeveloperCapabilitySet, ExecutionBudget, ProcessRunner, WorkspaceIO
from .capabilities.execution import BudgetExceeded
from .capabilities.policy import evaluate_runtime_boundary
from .config import RemediationRequest, ScannerConfig
from .deterministic.constraints import ConstraintEvaluator
from .deterministic.maven import MavenService
from .deterministic.repository import RepositoryPreparationError, RepositoryPreparer
from .deterministic.scanner import ScannerPreflightError, VulnerabilityScanner, create_scanner
from .deterministic.validation import DeterministicValidator
from .integrations.delivery import DeliveryAdapter, DeliveryContext, ManualDeliveryAdapter
from .journal import (
    CaptureStatus,
    DeliveryEligibility,
    JournalLifecycle,
    JournalPhase,
    JournalStore,
    RemediationOutcome,
    ValidationStatus,
    render_final_resolution,
)
from .models import (
    AgentTurnResult,
    DeliveryResult,
    Outcome,
    RepositoryBaseline,
    RunResult,
    ScanFailureKind,
    ScanReport,
    ValidationReport,
)
from .prompt import (
    compatibility_working_state,
    initial_message,
    intent_retry_message,
    outcome_message,
    outcome_retry_message,
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

    def run(self) -> RunResult:
        return asyncio.run(self.run_async())

    async def run_async(self) -> RunResult:
        workspace = RunWorkspace.create(self.request.workspace_parent)
        trace = TraceStore(workspace)
        trace.write_json("request.json", self.request.to_dict())
        lifecycle = JournalLifecycle(
            JournalStore(trace),
            trace,
            json.dumps(self._run_contract(None), indent=2, sort_keys=True),
            lambda: False,
            preliminary_contract=True,
        )
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
            return self._finish_with_journal(
                trace,
                lifecycle,
                RunResult(Outcome.BASELINE_FAILURE, f"RUNTIME_BOUNDARY_NOT_APPROVED: {boundary.reason}", str(workspace.root)),
                RemediationOutcome.BLOCKED,
                ValidationStatus.INCOMPLETE,
                DeliveryEligibility.NOT_DELIVERY_ELIGIBLE,
                None,
            )
        delivery_preflight = delivery_adapter.preflight(self.request)
        trace.write_json("delivery/preflight.json", delivery_preflight.to_dict())
        scanner = (
            create_scanner(self.request.scanner, workspace, process_runner, trace, maven_config=self.request.maven)
            if self.scanner_factory is create_scanner
            else self.scanner_factory(self.request.scanner, workspace, process_runner, trace)
        )
        try:
            baseline = self._prepare_baseline(workspace, trace, process_runner, scanner)
        except (ScannerPreflightError, RepositoryPreparationError, RuntimeError, BudgetExceeded) as exc:
            return self._finish_with_journal(
                trace,
                lifecycle,
                RunResult(Outcome.BASELINE_FAILURE, str(exc), str(workspace.root)),
                RemediationOutcome.FAILED,
                ValidationStatus.INCOMPLETE,
                DeliveryEligibility.NOT_DELIVERY_ELIGIBLE,
                None,
            )

        constraint_evaluator = ConstraintEvaluator()
        validator = DeterministicValidator(
            self.request, workspace, process_runner, scanner, constraint_evaluator, trace
        )
        lifecycle.set_repository_changed_probe(
            lambda: validator.repository_changed_since_cycle_start(lifecycle.active_cycle, baseline)
        )
        lifecycle.append_baseline_contract(
            json.dumps(self._run_contract(baseline), indent=2, sort_keys=True)
        )

        if self.request.vulnerability_ids and not baseline.target_findings:
            requested_ids = ", ".join(self.request.vulnerability_ids)
            return self._finish_with_journal(
                trace,
                lifecycle,
                RunResult(
                    Outcome.REQUESTED_VULNERABILITY_NOT_FOUND,
                    "REQUESTED_VULNERABILITY_NOT_FOUND: None of the requested vulnerability IDs "
                    f"were found in the completed baseline scan: {requested_ids}",
                    str(workspace.root),
                    baseline=baseline,
                    remediation_outcome=RemediationOutcome.NO_CHANGE_REQUIRED.value,
                    validation_status=ValidationStatus.INCOMPLETE.value,
                    capture_status=CaptureStatus.MISSING.value,
                    delivery_eligibility=DeliveryEligibility.NOT_DELIVERY_ELIGIBLE.value,
                ),
                RemediationOutcome.NO_CHANGE_REQUIRED,
                ValidationStatus.INCOMPLETE,
                DeliveryEligibility.NOT_DELIVERY_ELIGIBLE,
                None,
            )
        capabilities = DeveloperCapabilitySet(
            WorkspaceIO(workspace, trace), process_runner, budget, trace, lifecycle
        )
        agent_session = self.agent_session_factory(capabilities, self.request.model)
        message = initial_message(self.request, baseline)
        summaries: list[str] = []
        last_validation: ValidationReport | None = None
        last_delivery = DeliveryEligibility.NOT_DELIVERY_ELIGIBLE
        last_remediation = RemediationOutcome.INCONCLUSIVE
        agent_closed = False
        reason = "Configured remediation/validation cycle limit reached"
        try:
            for cycle in range(1, self.request.budget.max_cycles + 1):
                budget.ensure_time_remaining()
                validator.capture_cycle_start(cycle, baseline)
                lifecycle.begin_cycle(cycle)
                execution_turn = await self._run_until_intent(
                    agent_session, lifecycle, cycle, message
                )
                if not lifecycle.cycles[cycle].intent:
                    reason = "CYCLE_INTENT_CAPTURE_INCOMPLETE: bounded checkpoint recovery exhausted"
                    return self._finish_with_journal(
                        trace,
                        lifecycle,
                        RunResult(
                            Outcome.PARTIAL_MANUAL_REVIEW_REQUIRED,
                            reason,
                            str(workspace.root),
                            baseline=baseline,
                            cycles_completed=cycle - 1,
                            agent_summaries=tuple(summaries),
                        ),
                        RemediationOutcome.INCONCLUSIVE,
                        ValidationStatus.INCOMPLETE,
                        DeliveryEligibility.NOT_DELIVERY_ELIGIBLE,
                        last_validation,
                    )
                summaries.append(execution_turn.text)
                lifecycle.require_outcome()
                changed_files = validator.changed_files(baseline.commit)
                outcome_turn = await self._run_until_outcome(
                    agent_session,
                    lifecycle,
                    cycle,
                    execution_turn.text,
                    self._execution_evidence(trace, budget, changed_files),
                )
                capture = lifecycle.cycles[cycle]
                last_validation = validator.validate(cycle, baseline)
                validation_status = _validation_status(last_validation)
                last_delivery = _delivery_eligibility(
                    last_validation,
                    lifecycle.run_capture_status,
                    lifecycle.outcome_status(cycle),
                    delivery_preflight.eligible,
                )
                lifecycle.append_validation(last_validation, validation_status, last_delivery)
                trace.write_json(
                    f"agent/cycle-{cycle}.json",
                    {
                        "summary": execution_turn.text,
                        "workingState": compatibility_working_state(
                            capture.outcome_status, capture.outcome_answers
                        ),
                        "workingStateDeprecated": True,
                        "outcomeCaptureResponse": outcome_turn.text,
                        "captureStatus": capture.status.value,
                        "journalPath": str(lifecycle.store.path),
                        "intent": capture.intent.to_dict() if capture.intent else None,
                        "strategyCheckpoints": [
                            checkpoint.to_dict()
                            for checkpoint in capture.strategy_checkpoints
                        ],
                        "outcome": capture.outcome.to_dict() if capture.outcome else None,
                        "deterministicValidation": capture.validation.to_dict() if capture.validation else None,
                    },
                )
                trace.append_event(
                    "capture_classified", cycle=cycle, status=capture.status.value
                )
                trace.append_event(
                    "delivery_eligibility_determined",
                    cycle=cycle,
                    eligibility=last_delivery.value,
                )
                outcome_status = lifecycle.outcome_status(cycle)
                last_remediation = _remediation_outcome(last_validation, outcome_status)

                if _is_scanner_infrastructure_failure(last_validation.scan):
                    scan = last_validation.scan
                    reason = f"VALIDATION_SCANNER_FAILURE: {scan.effective_outcome.value}: {scan.error}"
                    break
                if last_validation.passed:
                    if not last_validation.changed_files:
                        reason = "No repository change requires delivery"
                        delivery = DeliveryResult(False, "NO_CHANGE_REQUIRED", reason=reason)
                        last_remediation = RemediationOutcome.NO_CHANGE_REQUIRED
                    elif last_delivery == DeliveryEligibility.FULL_AUTOMATIC_DELIVERY:
                        delivery = self._deliver(
                            delivery_adapter,
                            delivery_preflight.eligible,
                            workspace,
                            baseline,
                            last_validation,
                            summaries[-1],
                        )
                        reason = (
                            "Validated remediation delivered as a Draft PR"
                            if delivery.succeeded
                            else (delivery.reason or delivery.status)
                        )
                    else:
                        delivery = DeliveryResult(
                            False,
                            "VALIDATED_MANUAL_DELIVERY_REQUIRED",
                            reason="Validated work preserved, but capture or delivery policy requires manual review",
                            evidence={"diffPath": last_validation.diff_path, "treeDigest": last_validation.tree_digest},
                        )
                        reason = delivery.reason or delivery.status
                    outcome = Outcome.SUCCESS if delivery.succeeded else Outcome.PARTIAL_MANUAL_REVIEW_REQUIRED
                    await agent_session.close()
                    agent_closed = True
                    return self._finish_with_journal(
                        trace,
                        lifecycle,
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
                        last_remediation,
                        validation_status,
                        last_delivery,
                        last_validation,
                    )
                if budget.tool_calls >= self.request.budget.max_tool_calls or budget.remaining_seconds <= 0:
                    reason = "Configured operational budget reached"
                    break
                message = validation_feedback(last_validation, lifecycle.context(), cycle + 1)
        except BudgetExceeded as exc:
            reason = str(exc)
        except Exception as exc:
            reason = f"AGENT_RUNTIME_FAILURE: {exc}"
            if lifecycle.phase == JournalPhase.EXECUTION:
                cycle = lifecycle.active_cycle
                interrupted_summary = f"Execution turn failed before a normal response: {exc}"
                summaries.append(interrupted_summary)
                lifecycle.require_outcome()
                outcome_turn = AgentTurnResult("")
                try:
                    changed_files = validator.changed_files(baseline.commit)
                    outcome_turn = await self._run_until_outcome(
                        agent_session,
                        lifecycle,
                        cycle,
                        interrupted_summary,
                        {
                            **self._execution_evidence(trace, budget, changed_files),
                            "executionError": str(exc),
                        },
                    )
                except Exception as outcome_exc:
                    trace.append_event(
                        "outcome_capture_failed",
                        cycle=cycle,
                        error=str(outcome_exc),
                    )
                try:
                    last_validation = validator.validate(cycle, baseline)
                    validation_status = _validation_status(last_validation)
                    last_delivery = _delivery_eligibility(
                        last_validation,
                        lifecycle.run_capture_status,
                        lifecycle.outcome_status(cycle),
                        delivery_preflight.eligible,
                    )
                    lifecycle.append_validation(last_validation, validation_status, last_delivery)
                    capture = lifecycle.cycles[cycle]
                    trace.write_json(
                        f"agent/cycle-{cycle}.json",
                        {
                            "summary": interrupted_summary,
                            "workingState": compatibility_working_state(
                                capture.outcome_status, capture.outcome_answers
                            ),
                            "workingStateDeprecated": True,
                            "outcomeCaptureResponse": outcome_turn.text,
                            "captureStatus": capture.status.value,
                            "journalPath": str(lifecycle.store.path),
                            "intent": capture.intent.to_dict() if capture.intent else None,
                            "strategyCheckpoints": [
                                checkpoint.to_dict()
                                for checkpoint in capture.strategy_checkpoints
                            ],
                            "outcome": capture.outcome.to_dict() if capture.outcome else None,
                            "deterministicValidation": capture.validation.to_dict() if capture.validation else None,
                        },
                    )
                except (BudgetExceeded, RuntimeError) as validation_exc:
                    trace.append_event(
                        "post_failure_validation_incomplete",
                        cycle=cycle,
                        error=str(validation_exc),
                    )
        finally:
            if not agent_closed:
                try:
                    await agent_session.close()
                except Exception:
                    pass

        capture_status = lifecycle.run_capture_status
        validation_status = _validation_status(last_validation)
        if last_validation:
            last_delivery = _delivery_eligibility(
                last_validation,
                capture_status,
                lifecycle.outcome_status(),
                delivery_preflight.eligible,
            )
            last_remediation = _remediation_outcome(last_validation, lifecycle.outcome_status())
        result_outcome = (
            Outcome.PARTIAL_MANUAL_REVIEW_REQUIRED
            if (
                last_remediation in {RemediationOutcome.PARTIALLY_REMEDIATED, RemediationOutcome.BLOCKED, RemediationOutcome.FAILED}
                or reason.startswith("AGENT_RUNTIME_FAILURE:")
                or reason.startswith("VALIDATION_SCANNER_FAILURE:")
            )
            else Outcome.EXECUTION_LIMIT_REACHED
        )
        return self._finish_with_journal(
            trace,
            lifecycle,
            RunResult(
                result_outcome,
                reason,
                str(workspace.root),
                baseline=baseline,
                validation=last_validation,
                cycles_completed=len(summaries),
                agent_summaries=tuple(summaries),
            ),
            last_remediation,
            validation_status,
            last_delivery,
            last_validation,
        )

    def _prepare_baseline(
        self,
        workspace: RunWorkspace,
        trace: TraceStore,
        process_runner: ProcessRunner,
        scanner: VulnerabilityScanner,
    ) -> RepositoryBaseline:
        scanner.preflight(self.request.scanner)
        metadata = RepositoryPreparer(workspace, process_runner, trace).clone(
            self.request.repository_url, self.request.reference_branch
        )
        maven = MavenService(workspace.repository, process_runner, self.request.maven)
        build_results = maven.run_baseline(
            self.request.build_commands, self.request.test_commands, self.request.startup_commands
        )
        if not build_results or not all(result.succeeded for result in build_results):
            raise RuntimeError("Baseline Maven build failed")
        scan = scanner.scan(workspace.repository, self._baseline_scan_scope(), "baseline")
        if not scan.succeeded:
            raise RuntimeError(
                f"Baseline vulnerability scan failed ({scan.effective_outcome.value}): {scan.error}"
            )
        constraint_baseline = ConstraintEvaluator().capture(workspace.repository)
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
        return baseline

    async def _run_until_intent(
        self,
        session: AgentSession,
        lifecycle: JournalLifecycle,
        cycle: int,
        message: str,
    ) -> AgentTurnResult:
        turn = AgentTurnResult("")
        for _ in range(lifecycle.max_checkpoint_attempts):
            turn = await session.run_turn(message)
            if lifecycle.phase == JournalPhase.EXECUTION:
                return turn
            capture = lifecycle.cycles[cycle]
            errors = list(capture.last_intent_errors) or [
                "No Cycle Intent submission was received in the previous turn"
            ]
            message = intent_retry_message(cycle, errors)
        return turn

    async def _run_until_outcome(
        self,
        session: AgentSession,
        lifecycle: JournalLifecycle,
        cycle: int,
        execution_summary: str,
        evidence: dict,
    ) -> AgentTurnResult:
        message = outcome_message(cycle, execution_summary, evidence)
        turn = AgentTurnResult("")
        for _ in range(lifecycle.max_checkpoint_attempts):
            turn = await session.run_turn(message)
            if lifecycle.phase == JournalPhase.DETERMINISTIC_VALIDATION:
                return turn
            capture = lifecycle.cycles[cycle]
            errors = list(capture.last_outcome_errors) or [
                "No Cycle Outcome submission was received in the previous turn"
            ]
            message = outcome_retry_message(cycle, errors)
        return turn

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
            DeliveryContext(self.request, workspace, baseline, validation, agent_summary)
        )

    def _finish_with_journal(
        self,
        trace: TraceStore,
        lifecycle: JournalLifecycle,
        result: RunResult,
        remediation: RemediationOutcome,
        validation_status: ValidationStatus,
        delivery: DeliveryEligibility,
        validation: ValidationReport | None,
    ) -> RunResult:
        capture = lifecycle.run_capture_status
        first_capture = lifecycle.cycles.get(1)
        original_problem = (
            first_capture.intent_answers.get("Problem as received", "")
            if first_capture
            else ""
        )
        delivery_result = result.delivery.status if result.delivery else "No automatic delivery was performed."
        lifecycle.finish(
            render_final_resolution(
                remediation,
                original_problem or json.dumps(self._run_contract(result.baseline), sort_keys=True),
                lifecycle.cycles,
                validation,
                capture,
                delivery,
                delivery_result,
                "Restart/resume reconstruction is not implemented; machine events and the append-only journal remain available for audit.",
            )
        )
        projected = RunResult(
            **{
                **result.__dict__,
                "remediation_outcome": remediation.value,
                "validation_status": validation_status.value,
                "capture_status": capture.value,
                "capture_warnings": lifecycle.capture_warnings(),
                "delivery_eligibility": delivery.value,
                "journal_path": str(lifecycle.store.path),
            }
        )
        return self._finish(trace, projected)

    def _run_contract(self, baseline: RepositoryBaseline | None) -> dict:
        return {
            "objective": {
                "vulnerabilityIds": list(self.request.vulnerability_ids),
                "severityScope": list(self.request.severity_scope),
            },
            "constraints": self.request.to_dict()["constraints"],
            "completionCriteria": [
                "required build/test/startup commands pass",
                "fresh deterministic vulnerability scan succeeds",
                "requested target findings are absent",
                "no new prohibited findings are introduced",
                "typed constraints remain satisfied",
            ],
            "requiredCommands": {
                "build": list(self.request.build_commands),
                "test": list(self.request.test_commands),
                "startup": list(self.request.startup_commands),
            },
            "baseline": (
                {
                    "commit": baseline.commit,
                    "reference": baseline.reference,
                    "repositoryPath": baseline.repository_path,
                    "remoteUrl": baseline.remote_url,
                    "scanBackend": baseline.scan.backend,
                    "targetFindings": [finding.to_dict() for finding in baseline.target_findings],
                }
                if baseline
                else None
            ),
            "baselineCommandEvidence": (
                [
                    {
                        "command": result.command,
                        "exitCode": result.exit_code,
                        "timedOut": result.timed_out,
                        "blocked": result.blocked,
                    }
                    for result in baseline.build_results
                ]
                if baseline
                else []
            ),
            "budgets": self.request.to_dict()["budget"],
        }

    def _execution_evidence(
        self,
        trace: TraceStore,
        budget: ExecutionBudget,
        changed_files: tuple[str, ...],
    ) -> dict:
        events = []
        if trace.events_path.exists():
            for line in trace.events_path.read_text(encoding="utf-8").splitlines()[-100:]:
                event = json.loads(line)
                if event.get("type") == "command" and event.get("source") == "agent":
                    command = event.get("result", {})
                    events.append(
                        {
                            "type": "command",
                            "command": command.get("command"),
                            "exitCode": command.get("exitCode"),
                            "timedOut": command.get("timedOut"),
                            "blocked": command.get("blocked"),
                            "stdoutArtifact": command.get("stdoutArtifact"),
                            "stderrArtifact": command.get("stderrArtifact"),
                        }
                    )
                elif event.get("type") in {"workspace_edit", "tool_error", "agent_command_blocked"}:
                    events.append(event)
        return {
            "changedFiles": list(changed_files),
            "executionEvents": events[-40:],
            "remainingToolCalls": self.request.budget.max_tool_calls - budget.tool_calls,
            "remainingSeconds": budget.remaining_seconds,
        }

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


def _validation_status(report: ValidationReport | None) -> ValidationStatus:
    if report is None:
        return ValidationStatus.INCOMPLETE
    if report.passed:
        return ValidationStatus.PASSED
    if report.scan is None or not report.scan.succeeded:
        return ValidationStatus.INCOMPLETE
    return ValidationStatus.PARTIAL if _has_safe_partial_improvement(report) else ValidationStatus.FAILED


def _delivery_eligibility(
    report: ValidationReport,
    capture: CaptureStatus,
    outcome_status: str | None,
    automatic_delivery_available: bool = True,
) -> DeliveryEligibility:
    if (
        report.passed
        and report.changed_files
        and report.delivery_eligible
        and capture == CaptureStatus.COMPLETE
        and outcome_status == "READY_FOR_INDEPENDENT_VALIDATION"
        and automatic_delivery_available
    ):
        return DeliveryEligibility.FULL_AUTOMATIC_DELIVERY
    if (
        _validation_status(report) == ValidationStatus.PARTIAL
        and outcome_status == "PARTIALLY_REMEDIATED"
        and report.changed_files
        and not report.diagnostic_artifacts
        and capture in {CaptureStatus.COMPLETE, CaptureStatus.LATE, CaptureStatus.INCOMPLETE}
    ):
        return DeliveryEligibility.PARTIAL_MANUAL_REVIEW_DELIVERY
    return DeliveryEligibility.NOT_DELIVERY_ELIGIBLE


def _remediation_outcome(
    report: ValidationReport,
    outcome_status: str | None,
) -> RemediationOutcome:
    if report.passed:
        return RemediationOutcome.NO_CHANGE_REQUIRED if not report.changed_files else RemediationOutcome.FULLY_VALIDATED
    if _has_safe_partial_improvement(report):
        return RemediationOutcome.PARTIALLY_REMEDIATED
    if report.scan is None or not report.scan.succeeded:
        if outcome_status == "FAILED":
            return RemediationOutcome.FAILED
        if outcome_status == "BLOCKED":
            return RemediationOutcome.BLOCKED
        return RemediationOutcome.INCONCLUSIVE
    mapping = {
        "BLOCKED": RemediationOutcome.BLOCKED,
        "INCONCLUSIVE": RemediationOutcome.INCONCLUSIVE,
        "FAILED": RemediationOutcome.FAILED,
    }
    return mapping.get(outcome_status, RemediationOutcome.FAILED)


def _has_safe_partial_improvement(report: ValidationReport) -> bool:
    if not report.scan or not report.scan.succeeded or not report.target_comparison_complete:
        return False
    if not report.resolved_target_findings or not report.remaining_target_findings:
        return False
    if not report.changed_files or report.diagnostic_artifacts or not report.delivery_eligible:
        return False
    improvement_checks = [
        check for check in report.checks if check.name == "target_findings_improved"
    ]
    resolution_checks = [
        check for check in report.checks if check.name == "target_findings_resolved"
    ]
    scan_checks = [
        check for check in report.checks if check.name == "fresh_vulnerability_scan"
    ]
    if len(improvement_checks) != 1 or not improvement_checks[0].passed:
        return False
    if len(resolution_checks) != 1 or resolution_checks[0].passed:
        return False
    if len(scan_checks) != 1 or not scan_checks[0].passed:
        return False
    return all(
        check.passed
        for check in report.checks
        if check.name != "target_findings_resolved"
    )


def _is_scanner_infrastructure_failure(report: ScanReport | None) -> bool:
    return bool(report and not report.succeeded and report.failure_kind in _SCANNER_INFRASTRUCTURE_FAILURES)
