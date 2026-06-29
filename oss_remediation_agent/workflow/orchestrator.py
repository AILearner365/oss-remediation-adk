from __future__ import annotations

from pathlib import Path

from oss_remediation_agent.policies import RemediationPolicy
from oss_remediation_agent.tools.baseline_build_tool import run_baseline_build
from oss_remediation_agent.tools.repo_checkout_tool import checkout_baseline
from oss_remediation_agent.workspace import ManifestStore, WorkspaceManager


class WorkflowOrchestrator:
    """MVP orchestration skeleton.

    The orchestrator owns execution order and manifest updates. AI planning and
    outcome analysis remain integration points for the ADK application layer.
    """

    def __init__(self, workspace_root: str, policy: RemediationPolicy | None = None):
        self.workspace = WorkspaceManager(workspace_root)
        self.manifest_store = ManifestStore(Path(workspace_root) / "manifest.json")
        self.policy = policy or RemediationPolicy()

    def initialize(self, repository_url: str, reference_branch: str) -> dict:
        self.workspace.initialize()
        manifest = {
            "schemaVersion": "1.0",
            "artifactId": "manifest",
            "workflowId": "oss-remediation-mvp",
            "createdBy": "ADKWorkflowOrchestrator",
            "status": "INITIALIZED",
            "policy": self.policy.to_dict(),
            "repository": {"repositoryUrl": repository_url, "referenceBranch": reference_branch},
            "attempts": [],
            "acceptedPatchSet": {"patchIds": [], "vulnerabilityIds": [], "status": "EMPTY"},
        }
        self.manifest_store.save(manifest)
        return manifest

    def checkout_and_baseline(self, repository_url: str, reference_branch: str) -> dict:
        manifest = self.initialize(repository_url, reference_branch)
        checkout = checkout_baseline(repository_url, reference_branch, str(self.workspace.root))
        if checkout["status"] != "SUCCESS":
            manifest["status"] = "CHECKOUT_FAILED"
            self.manifest_store.save(manifest)
            return checkout

        repository_path = checkout["payload"]["repositoryPath"]
        baseline = run_baseline_build(
            repository_path,
            workflow_id=manifest["workflowId"],
            output_path=str(self.workspace.root / "baseline" / "baseline-build-result.json"),
            log_file=str(self.workspace.root / "baseline" / "baseline-build.log"),
        )
        manifest["status"] = "BASELINE_BUILD_PASSED" if baseline["status"] == "SUCCESS" else "BASELINE_BUILD_FAILED"
        manifest["baseline"] = {
            "repositoryPath": repository_path,
            "baselineBuildResult": "baseline/baseline-build-result.json",
        }
        self.manifest_store.save(manifest)
        return baseline
