from __future__ import annotations

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
        self.manifest_store.save(manifest)
        return result
