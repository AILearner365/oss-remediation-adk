from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from oss_remediation_agent.workflow.phase6_orchestrator import Phase6WorkflowOrchestrator


class Phase6PatchProgressOrchestrator(Phase6WorkflowOrchestrator):
    def run_patch_validation_attempt(self, attempt_number: int, patch_plan_path: str) -> dict:
        result = super().run_patch_validation_attempt(attempt_number, patch_plan_path)
        manifest = self.manifest_store.load()
        attempt_entry = self._attempt_entry(manifest, attempt_number)
        attempt_dir = self.workspace.root / f"attempt-{attempt_number}"
        artifacts = {
            "patchDryRunResult": attempt_dir / "patch-dry-run-result.json",
            "patchApplicationProof": attempt_dir / "patch-application-proof.json",
            "patchDiff": attempt_dir / "patch.diff",
        }
        for key, path in artifacts.items():
            if path.exists():
                attempt_entry[key] = self._relative_ref(str(path))
        self._enrich_accepted_patch_set_severity(manifest)
        self.manifest_store.save(manifest)
        return result

    def _enrich_accepted_patch_set_severity(self, manifest: dict[str, Any]) -> None:
        accepted = manifest.get("acceptedPatchSet") or {}
        if accepted.get("status") != "VALIDATED":
            return
        severity_by_vulnerability = self._severity_by_vulnerability_id(manifest)
        if not severity_by_vulnerability:
            return
        for row in accepted.get("remediationSummary", []) or []:
            vulnerability_id = row.get("vulnerabilityId")
            severity = severity_by_vulnerability.get(vulnerability_id)
            if severity:
                row["severity"] = severity
        for row in accepted.get("vulnerabilityDecisions", []) or []:
            vulnerability_id = row.get("vulnerabilityId")
            severity = severity_by_vulnerability.get(vulnerability_id)
            if severity:
                row["severity"] = severity

    def _severity_by_vulnerability_id(self, manifest: dict[str, Any]) -> dict[str, str]:
        assessment_ref = (manifest.get("baseline") or {}).get("vulnerabilityAssessmentReport")
        if not assessment_ref:
            return {}
        assessment_path = Path(assessment_ref)
        if not assessment_path.is_absolute():
            assessment_path = self.workspace.root / assessment_path
        if not assessment_path.exists():
            return {}
        try:
            assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        severity_by_id: dict[str, str] = {}
        for vulnerability in assessment.get("vulnerabilities", []) or []:
            vulnerability_id = vulnerability.get("vulnerabilityId")
            severity = vulnerability.get("severity")
            if vulnerability_id and severity:
                severity_by_id[str(vulnerability_id)] = str(severity)
        return severity_by_id
