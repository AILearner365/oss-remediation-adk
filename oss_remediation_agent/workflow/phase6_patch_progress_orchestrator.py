from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from oss_remediation_agent.workflow.phase6_orchestrator import Phase6WorkflowOrchestrator


class Phase6PatchProgressOrchestrator(Phase6WorkflowOrchestrator):
    def run_patch_validation_attempt(self, attempt_number: int, patch_plan_path: str) -> dict:
        self._remove_redundant_transitive_dependency_management_overrides(patch_plan_path)
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

    def _remove_redundant_transitive_dependency_management_overrides(self, patch_plan_path: str) -> None:
        """Prefer parent-bump validation over same-attempt transitive overrides.

        If a transitive vulnerable dependency is introduced by a direct dependency
        that is already patched in the same plan, do not also add a
        dependencyManagement override for the transitive dependency. The parent
        bump should be validated first; a transitive override is only appropriate
        after validation proves the parent bump did not resolve it, or when no
        safe parent bump exists.
        """
        plan_path = Path(patch_plan_path)
        if not plan_path.is_absolute():
            plan_path = self.workspace.root / plan_path
        if not plan_path.exists():
            return
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except Exception:
            return
        if plan.get("decisionType") != "PATCH_PLAN":
            return

        analyzer = self._read_project_analyzer_report(plan)
        if not analyzer:
            return
        dependency_evidence = analyzer.get("dependencyResolutionEvidence", []) or []
        direct_dependencies = {
            item.get("dependency")
            for item in dependency_evidence
            if item.get("dependency") and item.get("dependencyType") == "DIRECT"
        }
        transitive_introducer_by_dependency = {
            item.get("dependency"): item.get("introducedBy")
            for item in dependency_evidence
            if item.get("dependency")
            and item.get("dependencyType") == "TRANSITIVE"
            and item.get("introducedBy")
        }

        patched_direct_dependencies: set[str] = set()
        patch_ids_by_dependency: dict[str, list[str]] = {}
        for decision in plan.get("vulnerabilityDecisions", []) or []:
            dependency = self._decision_dependency_coordinate(decision)
            if not dependency or dependency not in direct_dependencies:
                continue
            patch_ids = [
                patch.get("patchId")
                for patch in decision.get("patches", []) or []
                if patch.get("patchId") and patch.get("changeType") != "DEPENDENCY_MANAGEMENT_OVERRIDE"
            ]
            if patch_ids:
                patched_direct_dependencies.add(dependency)
                patch_ids_by_dependency[dependency] = patch_ids

        if not patched_direct_dependencies:
            return

        changed = False
        warnings = plan.setdefault("warnings", [])
        for decision in plan.get("vulnerabilityDecisions", []) or []:
            dependency = self._decision_dependency_coordinate(decision)
            introduced_by = transitive_introducer_by_dependency.get(dependency)
            if not dependency or not introduced_by or introduced_by not in patched_direct_dependencies:
                continue
            patches = decision.get("patches", []) or []
            retained_patches = [
                patch
                for patch in patches
                if patch.get("changeType") != "DEPENDENCY_MANAGEMENT_OVERRIDE"
            ]
            if len(retained_patches) == len(patches):
                continue

            removed_patch_ids = [
                patch.get("patchId")
                for patch in patches
                if patch.get("changeType") == "DEPENDENCY_MANAGEMENT_OVERRIDE" and patch.get("patchId")
            ]
            decision["patches"] = retained_patches
            decision["transitiveRemediationStrategy"] = "IMPLICIT_PARENT_BUMP"
            decision["resolvedByDependency"] = introduced_by
            decision["coveredByPatchIds"] = patch_ids_by_dependency.get(introduced_by, [])
            decision["statusReason"] = (
                f"DependencyManagement override removed because {dependency} is a transitive dependency "
                f"introduced by {introduced_by}, and {introduced_by} is already patched in this plan. "
                "Validation must confirm whether the parent dependency upgrade resolves the transitive vulnerability."
            )
            warnings.append(
                f"Removed redundant DEPENDENCY_MANAGEMENT_OVERRIDE patch(es) {removed_patch_ids} for {dependency}; "
                f"covered by parent dependency patch for {introduced_by}."
            )
            changed = True

        if not changed:
            return

        summary = plan.setdefault("summary", {})
        summary["patchDecisionCount"] = sum(
            1
            for decision in plan.get("vulnerabilityDecisions", []) or []
            if decision.get("decision") == "PATCH" and bool(decision.get("patches"))
        )
        plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _accepted_patch_set(self, attempt_number: int, patch_plan_path: str, patch_proof_path: str, validation_result_ref: str) -> dict:
        plan = self._read_json(patch_plan_path)
        proof = self._read_json(patch_proof_path)
        applied_patch_ids = {item.get("patchId") for item in proof.get("patchResults", []) if item.get("status") == "APPLIED"}
        vulnerability_ids = []
        remediation_summary = []
        accepted_decisions = []
        for decision in plan.get("vulnerabilityDecisions", []):
            patch_ids = {patch.get("patchId") for patch in decision.get("patches", [])}
            covered_patch_ids = {patch_id for patch_id in decision.get("coveredByPatchIds", []) if patch_id}
            implicit_parent_bump = decision.get("transitiveRemediationStrategy") == "IMPLICIT_PARENT_BUMP"
            if patch_ids and patch_ids.issubset(applied_patch_ids):
                vulnerability_id = decision.get("vulnerabilityId")
                vulnerability_ids.append(vulnerability_id)
                row = self._remediation_row(decision)
                remediation_summary.append(row)
                accepted_decisions.append({
                    "vulnerabilityId": vulnerability_id,
                    "decision": decision.get("decision", "PATCH"),
                    "patchIds": sorted(item for item in patch_ids if item),
                    "dependency": row.get("dependency"),
                    "oldVersion": row.get("oldVersion"),
                    "newVersion": row.get("newVersion"),
                })
            elif implicit_parent_bump and covered_patch_ids and covered_patch_ids.issubset(applied_patch_ids):
                vulnerability_id = decision.get("vulnerabilityId")
                vulnerability_ids.append(vulnerability_id)
                row = self._remediation_row(decision)
                row["status"] = "REMEDIATED"
                row["statusReason"] = decision.get("statusReason") or (
                    "Validated implicitly through the parent dependency upgrade. No direct dependencyManagement override was applied."
                )
                row["remediationType"] = "IMPLICIT_PARENT_BUMP"
                row["resolvedByDependency"] = decision.get("resolvedByDependency")
                row["coveredByPatchIds"] = sorted(covered_patch_ids)
                remediation_summary.append(row)
                accepted_decisions.append({
                    "vulnerabilityId": vulnerability_id,
                    "decision": decision.get("decision", "PATCH"),
                    "patchIds": [],
                    "coveredByPatchIds": sorted(covered_patch_ids),
                    "dependency": row.get("dependency"),
                    "oldVersion": row.get("oldVersion"),
                    "newVersion": row.get("newVersion"),
                    "remediationType": "IMPLICIT_PARENT_BUMP",
                    "resolvedByDependency": decision.get("resolvedByDependency"),
                })
        return {
            "patchSetId": f"accepted-patch-set-{attempt_number}",
            "status": "VALIDATED",
            "sourceAttempts": [attempt_number],
            "patchIds": sorted(item for item in applied_patch_ids if item),
            "vulnerabilityIds": sorted(item for item in vulnerability_ids if item),
            "validationResult": validation_result_ref,
            "appliesOnBaselineCommit": self.manifest_store.load().get("repository", {}).get("baselineCommit"),
            "remediationSummary": remediation_summary,
            "vulnerabilityDecisions": accepted_decisions,
        }

    def _read_project_analyzer_report(self, plan: dict[str, Any]) -> dict[str, Any]:
        analyzer_ref = (plan.get("artifactReferences") or {}).get("projectAnalyzerReport")
        if not analyzer_ref:
            analyzer_ref = "baseline/project-analyzer-report.json"
        analyzer_path = Path(analyzer_ref)
        if not analyzer_path.is_absolute():
            analyzer_path = self.workspace.root / analyzer_path
        if not analyzer_path.exists():
            return {}
        try:
            return json.loads(analyzer_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    @staticmethod
    def _decision_dependency_coordinate(decision: dict[str, Any]) -> str | None:
        dependency = decision.get("dependency") or {}
        if isinstance(dependency, str):
            return dependency
        package_name = dependency.get("packageName")
        if package_name:
            return package_name
        group_id = dependency.get("groupId")
        artifact_id = dependency.get("artifactId")
        if group_id and artifact_id:
            return f"{group_id}:{artifact_id}"
        return artifact_id or group_id

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
