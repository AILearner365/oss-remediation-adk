from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from ..capabilities.execution import ProcessRunner
from ..config import RemediationRequest
from ..evidence import is_generated_evidence_path
from ..models import (
    RepositoryBaseline,
    RepositoryCycleEvidence,
    ScanReport,
    ValidationCheck,
    ValidationReport,
    VulnerabilityFinding,
)
from ..workspace import RunWorkspace, TraceStore, sha256_file
from .constraints import ConstraintEvaluator
from .diff_summary import bound_line_changes, parse_line_changes
from .maven import MavenService
from .scanner import ScannerPreflightError, VulnerabilityScanner


_SCANNED_PACKAGE_COUNT_RE = re.compile(r"found\s+(\d+)\s+packages?\b", re.IGNORECASE)
_FILTERED_UNSCANNABLE_RE = re.compile(
    r"Filtered\s+(\d+)\s+local/unscannable\s+package/s\s+from\s+the\s+scan",
    re.IGNORECASE,
)


def _scanner_stderr(report: ScanReport | None) -> str:
    if report is None:
        return ""
    if report.command_result is not None:
        return report.command_result.stderr or ""
    for attempt in reversed(report.attempts):
        command_result = attempt.get("commandResult") if isinstance(attempt, dict) else None
        if isinstance(command_result, dict):
            stderr = command_result.get("stderr")
            if isinstance(stderr, str):
                return stderr
    return ""


def _osv_package_coverage(report: ScanReport | None) -> dict[str, int | None]:
    if report is None or report.backend.lower() != "osv":
        return {"extractedPackages": None, "filteredUnscannablePackages": None, "scannablePackages": None}
    stderr = _scanner_stderr(report)
    counts = [int(value) for value in _SCANNED_PACKAGE_COUNT_RE.findall(stderr)]
    filtered_matches = [int(value) for value in _FILTERED_UNSCANNABLE_RE.findall(stderr)]
    extracted = sum(counts) if counts else None
    filtered = max(filtered_matches) if filtered_matches else 0
    scannable = None if extracted is None else max(extracted - filtered, 0)
    return {
        "extractedPackages": extracted,
        "filteredUnscannablePackages": filtered,
        "scannablePackages": scannable,
    }


def _target_comparison_coverage(
    baseline_scan: ScanReport,
    current_scan: ScanReport | None,
    *,
    build_passed: bool,
) -> tuple[bool, str | None, dict[str, object]]:
    baseline_coverage = _osv_package_coverage(baseline_scan)
    current_coverage = _osv_package_coverage(current_scan)
    evidence: dict[str, object] = {
        "baseline": baseline_coverage,
        "current": current_coverage,
        "buildPassed": build_passed,
    }
    if current_scan is None or not current_scan.succeeded:
        return False, "fresh vulnerability scan did not complete", evidence
    if not build_passed:
        return False, "build/test validation failed, so dependency scan coverage is not authoritative", evidence
    if current_scan.backend.lower() != "osv":
        return True, None, evidence

    baseline_scannable = baseline_coverage["scannablePackages"]
    current_scannable = current_coverage["scannablePackages"]
    current_filtered = current_coverage["filteredUnscannablePackages"]

    if current_filtered and current_coverage["extractedPackages"] is None:
        return False, "OSV reported local/unscannable packages but package coverage could not be measured", evidence
    if isinstance(baseline_scannable, int) and baseline_scannable > 0:
        if not isinstance(current_scannable, int):
            return False, "OSV package coverage could not be measured against the baseline", evidence
        if current_scannable < baseline_scannable:
            return (
                False,
                "OSV scannable package coverage regressed below the baseline; absent findings are UNKNOWN",
                evidence,
            )
    elif isinstance(current_scannable, int) and current_scannable == 0 and current_filtered:
        return False, "OSV filtered all extracted packages as local/unscannable; absent findings are UNKNOWN", evidence
    return True, None, evidence


def _classify_target_findings(
    baseline_targets: Iterable[VulnerabilityFinding],
    final_findings: Iterable[VulnerabilityFinding],
    *,
    comparison_complete: bool,
) -> tuple[list[dict], list[dict], list[dict]]:
    final = tuple(final_findings)
    resolved: list[dict] = []
    remaining: list[dict] = []
    unknown: list[dict] = []
    for target in baseline_targets:
        if any(target.matches(current) for current in final):
            remaining.append(target.to_dict())
        elif comparison_complete:
            resolved.append(target.to_dict())
        else:
            unknown.append(target.to_dict())
    return resolved, remaining, unknown


class DeterministicValidator:
    def __init__(
        self,
        request: RemediationRequest,
        workspace: RunWorkspace,
        process_runner: ProcessRunner,
        scanner: VulnerabilityScanner,
        constraints: ConstraintEvaluator,
        trace: TraceStore,
    ):
        self.request = request
        self.workspace = workspace
        self.process_runner = process_runner
        self.scanner = scanner
        self.constraints = constraints
        self.trace = trace
        self._cycle_starts: dict[int, _RepositoryState] = {}
        self._completed_cycle_digests: dict[int, str] = {}

    def capture_cycle_start(self, cycle: int, baseline: RepositoryBaseline) -> None:
        changed_files, captured = self._capture_changed_files(baseline.commit)
        self._cycle_starts[cycle] = self._repository_state(changed_files, captured)

    def repository_changed_since_cycle_start(self, cycle: int, baseline: RepositoryBaseline) -> bool | None:
        before = self._cycle_starts.get(cycle)
        if before is None or not before.captured:
            return None
        changed_files, captured = self._capture_changed_files(baseline.commit)
        after = self._repository_state(changed_files, captured)
        return before.file_digests != after.file_digests if captured else None

    def validate(self, cycle: int, baseline: RepositoryBaseline) -> ValidationReport:
        checks: list[ValidationCheck] = []
        based_on_baseline = self.process_runner.run_argv(
            ["git", "merge-base", "--is-ancestor", baseline.commit, "HEAD"],
            cwd=self.workspace.repository,
            source=f"validation_{cycle}_git_base",
        )
        checks.append(
            ValidationCheck(
                "baseline_ancestry",
                based_on_baseline.succeeded,
                "Repository remains based on the recorded baseline" if based_on_baseline.succeeded else "Repository ancestry no longer includes the baseline",
                based_on_baseline.to_dict(),
            )
        )
        changed_files, status_succeeded = self._capture_changed_files(baseline.commit)
        after_state = self._repository_state(changed_files, status_succeeded)
        before_state = self._cycle_starts.pop(cycle, after_state)
        cycle_evidence = self._cycle_evidence(cycle, before_state, after_state)
        diff_text, diff_succeeded = self._capture_diff_text(baseline.commit, changed_files)
        checks.append(
            ValidationCheck(
                "git_change_evidence",
                status_succeeded and diff_succeeded,
                "Git status and full diff were captured" if status_succeeded and diff_succeeded else "Git change evidence could not be captured",
            )
        )
        diff_path = self.trace.write_text(f"validation/cycle-{cycle}.diff", diff_text)
        build_results = MavenService(
            self.workspace.repository,
            self.process_runner,
            self.request.maven,
        ).run_validation(
            self.request.build_commands,
            self.request.test_commands,
            self.request.startup_commands,
        )
        build_passed = bool(build_results) and all(result.succeeded for result in build_results)
        checks.append(
            ValidationCheck(
                "build_test_startup",
                build_passed,
                "Required build/test/startup commands passed" if build_passed else "A required build/test/startup command failed",
                {"results": [result.to_dict() for result in build_results]},
            )
        )
        scan_report = None
        try:
            scan_report = self.scanner.scan(self.workspace.repository, self._scan_scope(), f"validation-cycle-{cycle}")
            checks.append(
                ValidationCheck(
                    "fresh_vulnerability_scan",
                    scan_report.succeeded,
                    (
                        f"Fresh vulnerability scan completed: {scan_report.effective_outcome.value}"
                        if scan_report.succeeded
                        else f"Fresh vulnerability scan incomplete: {scan_report.effective_outcome.value}"
                    ),
                    scan_report.to_dict(),
                )
            )
        except ScannerPreflightError as exc:
            checks.append(ValidationCheck("fresh_vulnerability_scan", False, str(exc)))
        scan_succeeded = bool(scan_report and scan_report.succeeded)
        final_findings = scan_report.findings if scan_succeeded else ()
        target_comparison_complete, comparison_reason, coverage_evidence = _target_comparison_coverage(
            baseline.scan,
            scan_report,
            build_passed=build_passed,
        )
        resolved_targets, remaining_targets, unknown_targets = _classify_target_findings(
            baseline.target_findings,
            final_findings,
            comparison_complete=target_comparison_complete,
        )
        comparison_unavailable_message = (
            "Target comparison unavailable because validation evidence is incomplete"
            + (f": {comparison_reason}" if comparison_reason else "")
        )
        checks.append(
            ValidationCheck(
                "target_findings_improved",
                target_comparison_complete
                and (not baseline.target_findings or bool(resolved_targets)),
                (
                    comparison_unavailable_message
                    if not target_comparison_complete
                    else f"{len(resolved_targets)} of {len(baseline.target_findings)} original target findings are resolved"
                    if resolved_targets
                    else (
                        "No original target finding was present in the baseline"
                        if not baseline.target_findings
                        else "No original target finding was resolved"
                    )
                ),
                {
                    "resolved": resolved_targets,
                    "remaining": remaining_targets,
                    "unknown": unknown_targets,
                    "baselineTargetCount": len(baseline.target_findings),
                    "comparisonComplete": target_comparison_complete,
                    "coverage": coverage_evidence,
                },
            )
        )
        checks.append(
            ValidationCheck(
                "target_findings_resolved",
                target_comparison_complete and not remaining_targets and not unknown_targets,
                (
                    comparison_unavailable_message
                    if not target_comparison_complete
                    else "Requested target findings are resolved"
                    if not remaining_targets and not unknown_targets
                    else "Requested target findings remain"
                ),
                {
                    "remaining": remaining_targets,
                    "unknown": unknown_targets,
                    "comparisonComplete": target_comparison_complete,
                    "coverage": coverage_evidence,
                },
            )
        )
        prohibited = set(self.request.constraints.prohibited_new_severities)
        baseline_findings = baseline.scan.findings
        new_findings = [
            finding.to_dict()
            for finding in final_findings
            if finding.severity in prohibited and not any(finding.matches(existing) for existing in baseline_findings)
        ]
        checks.append(
            ValidationCheck(
                "no_new_prohibited_findings",
                not new_findings and target_comparison_complete,
                (
                    "New prohibited finding comparison unavailable because the fresh scan did not complete"
                    if not target_comparison_complete
                    else "No new prohibited findings were introduced"
                    if not new_findings
                    else "New prohibited findings were introduced"
                ),
                {
                    "newFindings": new_findings,
                    "comparisonComplete": target_comparison_complete,
                },
            )
        )
        checks.extend(
            self.constraints.validate(
                self.workspace.repository,
                baseline.constraints,
                self.request.constraints,
                changed_files,
                diff_text,
            )
        )
        diagnostic_artifacts = tuple(
            relative for relative in changed_files if _is_likely_diagnostic_artifact(relative)
        )
        checks.append(
            ValidationCheck(
                "delivery_diff_hygiene",
                not diagnostic_artifacts,
                (
                    "No newly changed likely investigation-only artifacts were detected"
                    if not diagnostic_artifacts
                    else "Likely investigation-only artifacts require cleanup or manual review"
                ),
                {"diagnosticArtifacts": list(diagnostic_artifacts)},
            )
        )
        digest = self.tree_digest(changed_files)
        delivery_eligible = not self.request.constraints.unenforced_constraints and not diagnostic_artifacts
        warnings = tuple(
            f"Constraint is not deterministically enforced: {constraint}"
            for constraint in self.request.constraints.unenforced_constraints
        )
        report = ValidationReport(
            cycle=cycle,
            passed=all(check.passed for check in checks),
            checks=tuple(checks),
            changed_files=changed_files,
            diff_path=str(diff_path),
            tree_digest=digest,
            scan=scan_report,
            delivery_eligible=delivery_eligible,
            warnings=warnings,
            cycle_evidence=cycle_evidence,
            diagnostic_artifacts=diagnostic_artifacts,
            resolved_target_findings=tuple(resolved_targets),
            remaining_target_findings=tuple(remaining_targets),
            unknown_target_findings=tuple(unknown_targets),
            target_comparison_complete=target_comparison_complete,
        )
        self.trace.write_json(f"validation/cycle-{cycle}.json", report.to_dict())
        self.trace.append_event("validation", cycle=cycle, passed=report.passed, treeDigest=digest)
        if after_state.captured:
            self._completed_cycle_digests[cycle] = after_state.digest
        return report

    def _repository_state(
        self,
        changed_files: tuple[str, ...],
        captured: bool,
    ) -> "_RepositoryState":
        file_digests: dict[str, str] = {}
        for relative in changed_files:
            path = self.workspace.repository / relative
            if path.is_symlink():
                value = f"symlink:{path.readlink()}"
            elif path.is_file():
                value = f"file:{path.stat().st_mode & 0o777:o}:{sha256_file(path)}"
            else:
                value = "deleted"
            file_digests[relative] = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return _RepositoryState(
            digest=self.tree_digest(changed_files),
            changed_files=changed_files,
            file_digests=file_digests,
            captured=captured,
        )

    def _cycle_evidence(
        self,
        cycle: int,
        before: "_RepositoryState",
        after: "_RepositoryState",
    ) -> RepositoryCycleEvidence:
        before_paths = set(before.file_digests)
        after_paths = set(after.file_digests)
        added = tuple(sorted(after_paths - before_paths))
        removed = tuple(sorted(before_paths - after_paths))
        modified = tuple(
            sorted(
                path
                for path in before_paths & after_paths
                if before.file_digests[path] != after.file_digests[path]
            )
        )
        matches_prior_cycle = next(
            (
                prior_cycle
                for prior_cycle, digest in self._completed_cycle_digests.items()
                if after.captured and digest == after.digest
            ),
            None,
        )
        delta_payload = {
            "cycle": cycle,
            "before": {
                "captured": before.captured,
                "stateDigest": before.digest,
                "changedFiles": list(before.changed_files),
                "fileDigests": before.file_digests,
            },
            "after": {
                "captured": after.captured,
                "stateDigest": after.digest,
                "changedFiles": list(after.changed_files),
                "fileDigests": after.file_digests,
            },
            "delta": {
                "pathsAddedToChangeSet": list(added),
                "pathsModifiedSinceCycleStart": list(modified),
                "pathsRemovedFromChangeSet": list(removed),
                "repositoryStateChanged": before.file_digests != after.file_digests,
                "matchesPriorCycle": matches_prior_cycle,
            },
        }
        delta_path = self.trace.write_json(
            f"validation/cycle-{cycle}-repository-delta.json",
            delta_payload,
        )
        return RepositoryCycleEvidence(
            before_state_digest=before.digest,
            after_state_digest=after.digest,
            before_changed_files=before.changed_files,
            after_changed_files=after.changed_files,
            paths_added_to_change_set=added,
            paths_modified_since_cycle_start=modified,
            paths_removed_from_change_set=removed,
            repository_state_changed=before.file_digests != after.file_digests,
            matches_prior_cycle=matches_prior_cycle,
            delta_path=str(delta_path),
            before_state_captured=before.captured,
            after_state_captured=after.captured,
        )

    def changed_files(self, baseline_commit: str = "HEAD") -> tuple[str, ...]:
        return self._capture_changed_files(baseline_commit)[0]

    def _capture_changed_files(self, baseline_commit: str) -> tuple[tuple[str, ...], bool]:
        result = self.process_runner.run_argv(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=self.workspace.repository,
            source="git_status",
        )
        if not result.succeeded:
            return (), False
        output = _full_stdout(result)
        paths: list[str] = []
        records = output.split("\0")
        index = 0
        while index < len(records):
            record = records[index]
            index += 1
            if len(record) < 4:
                continue
            status = record[:2]
            path = record[3:]
            normalized_path = path.replace("\\", "/")
            if status != "??" or not is_generated_evidence_path(normalized_path):
                paths.append(normalized_path)
            if "R" in status or "C" in status:
                index += 1
        baseline_diff = self.process_runner.run_argv(
            ["git", "diff", "--name-only", "-z", baseline_commit],
            cwd=self.workspace.repository,
            source="git_changed_since_baseline",
        )
        if not baseline_diff.succeeded:
            return tuple(sorted(set(paths))), False
        paths.extend(
            value.replace("\\", "/")
            for value in _full_stdout(baseline_diff).split("\0")
            if value
        )
        return tuple(sorted(set(paths))), True

    def diff_text(self, baseline_commit: str, changed_files: tuple[str, ...]) -> str:
        return self._capture_diff_text(baseline_commit, changed_files)[0]

    def outcome_change_evidence(self, cycle: int, baseline_commit: str) -> dict:
        """Capture net authoritative changes before Outcome; this is not validation."""
        files, status_ok = self._capture_changed_files(baseline_commit)
        diff, diff_ok = self._capture_diff_text(baseline_commit, files)
        path = self.trace.write_text(f"outcome/cycle-{cycle}.diff", diff)
        parsed_changes = parse_line_changes(diff)
        line_changes = bound_line_changes(parsed_changes, 12, 20)
        snapshot = {
            "workspaceKind": "authoritative", "cycle": cycle,
            "capturedAt": datetime.now(timezone.utc).isoformat(),
            "baselineCommit": baseline_commit, "captureSucceeded": status_ok and diff_ok,
            "changedFiles": list(files), "diffReference": self.trace.issue_evidence_reference(path),
            "changedFilesComplete": status_ok,
            "diffSha256": hashlib.sha256(diff.encode("utf-8")).hexdigest(),
            "diff": diff, "lineChanges": line_changes,
            "diffComplete": diff_ok, "lineChangesComplete": True,
            "lineChangeParsingComplete": diff_ok and all(change["countsComplete"] for change in line_changes),
            "summaryRecovery": "For incomplete or unsupported summaries, retrieve diffReference for the full captured diff; snapshotReference retains all file summaries. Check captureSucceeded before treating the captured diff as complete repository evidence.",
            "treeDigest": self.tree_digest(files),
            "independentValidationAtCapture": "not yet run",
        }
        manifest = self.trace.write_json(f"outcome/cycle-{cycle}-state.json", snapshot)
        displayed_changes = bound_line_changes(parsed_changes[:8], 6, 12)
        return {**snapshot, "changedFiles": list(files[:40]), "changedFilesComplete": status_ok and len(files) <= 40,
                "lineChanges": displayed_changes, "lineChangesComplete": len(line_changes) <= 8,
                "diff": diff[:12000], "diffComplete": diff_ok and len(diff) <= 12000,
                "snapshotReference": self.trace.issue_evidence_reference(manifest)}

    def _capture_diff_text(self, baseline_commit: str, changed_files: tuple[str, ...]) -> tuple[str, bool]:
        result = self.process_runner.run_argv(
            ["git", "diff", "--binary", "--no-ext-diff", baseline_commit],
            cwd=self.workspace.repository,
            source="git_diff",
        )
        sections = [_full_stdout(result)]
        for relative in changed_files:
            path = self.workspace.repository / relative
            tracked = self.process_runner.run_argv(
                ["git", "ls-files", "--error-unmatch", "--", relative],
                cwd=self.workspace.repository,
                source="git_tracked_check",
            )
            if tracked.succeeded or not path.is_file():
                continue
            data = path.read_bytes()
            try:
                content = data.decode("utf-8")
                lines = content.split("\n")
                if lines[-1] == "":
                    lines.pop()
                prefixed = "\n".join(f"+{line}" for line in lines)
                hunk = f"@@ -0,0 +1,{len(lines)} @@\n{prefixed}\n" if lines else ""
                if content and not content.endswith("\n"):
                    hunk += "\\ No newline at end of file\n"
                sections.append(f"diff --git a/{relative} b/{relative}\nnew file mode 100644\n--- /dev/null\n+++ b/{relative}\n{hunk}")
            except UnicodeDecodeError:
                sections.append(f"diff --git a/{relative} b/{relative}\nBinary files /dev/null and b/{relative} differ\n"
                                f"Binary untracked file {relative} sha256={hashlib.sha256(data).hexdigest()} size={len(data)}\n")
        return "\n".join(section for section in sections if section), result.succeeded

    def tree_digest(self, changed_files: Iterable[str]) -> str:
        digest = hashlib.sha256()
        for relative in sorted(changed_files):
            digest.update(relative.encode("utf-8"))
            path = self.workspace.repository / relative
            if path.is_symlink():
                digest.update(b"<symlink>")
                digest.update(str(path.readlink()).encode("utf-8"))
            elif path.is_file():
                digest.update(f"<mode:{path.stat().st_mode & 0o777:o}>".encode("ascii"))
                digest.update(sha256_file(path).encode("ascii"))
            else:
                digest.update(b"<deleted>")
        return digest.hexdigest()

    def _scan_scope(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.request.severity_scope) | set(self.request.constraints.prohibited_new_severities)))


def _full_stdout(result) -> str:
    if result.stdout_artifact:
        return Path(result.stdout_artifact).read_text(encoding="utf-8")
    return result.stdout


@dataclass(frozen=True)
class _RepositoryState:
    digest: str
    changed_files: tuple[str, ...]
    file_digests: dict[str, str]
    captured: bool


_DIAGNOSTIC_ARTIFACT = re.compile(
    r"(?i)(?:^|/)(?:dependency[-_ ]?tree|dependency[-_ ]?graph|diagnostic[-_ ]?report|investigation[-_ ]?notes?)"
    r"(?:\.[a-z0-9._-]+)?$"
)


def _is_likely_diagnostic_artifact(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/")
    return bool(_DIAGNOSTIC_ARTIFACT.search(normalized))
