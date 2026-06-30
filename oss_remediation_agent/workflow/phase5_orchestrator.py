from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from oss_remediation_agent.workflow.orchestrator import WorkflowOrchestrator
from oss_remediation_agent.tools.generic_patch_apply_tool import apply as apply_patch_plan


class Phase5WorkflowOrchestrator(WorkflowOrchestrator):
    """Phase 5 aligned orchestration refinements.

    This subclass keeps the existing tool wiring from WorkflowOrchestrator but
    corrects the remaining lifecycle semantics:

    * planning-only cycles do not prepare an attempt workspace or consume a
      remediation attempt;
    * attempt workspace preparation happens lazily when patch execution starts;
    * accepted patch set replay replays only validated accepted patch IDs, not
      the full historical patch plan.
    """

    def run_orchestration_loop(
        self,
        progress: list[dict[str, Any]] | None = None,
        first_planning_agent_output: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        progress = progress if progress is not None else []
        attempt_number = 1
        injected_output = first_planning_agent_output

        while attempt_number <= self.policy.max_attempts:
            planning_result = self.run_planning_agent_boundary(
                attempt_number=attempt_number,
                planning_agent_output=injected_output,
            )
            injected_output = None
            self._record(progress, f"remediation_planning_agent_attempt_{attempt_number}", planning_result)
            if planning_result.get("status") != "SUCCESS":
                return self.runtime_summary(
                    progress,
                    "Workflow stopped because the Planning Agent did not return usable structured output.",
                )

            routed = self.handle_planner_result(planning_result, attempt_number=attempt_number)
            self._record(progress, f"planner_result_routing_attempt_{attempt_number}", routed)

            if routed.get("status") == "ADDITIONAL_INVESTIGATION_COMPLETE":
                # Additional investigation does not consume a remediation attempt.
                continue

            if routed.get("failureCode") == "PLANNING_CONSTRAINT_VIOLATION":
                return self.runtime_summary(
                    progress,
                    "Workflow stopped because the Planning Agent violated the investigation-limit constraint.",
                )

            if routed.get("status") in {"MANUAL_REVIEW_REQUIRED", "PR_SUMMARY_CREATED", "SUCCESS"}:
                return self.runtime_summary(progress, "Workflow reached a terminal routing decision.")

            manifest = self.manifest_store.load()
            if manifest.get("status") == "OUTCOME_ANALYSIS_AGENT_INVOCATION_FAILED":
                return self.runtime_summary(progress, "Workflow stopped because Outcome Analysis Agent invocation failed.")

            if manifest.get("status") == "OUTCOME_ANALYSIS_COMPLETE":
                manifest["status"] = "REPLANNING"
                self.manifest_store.save(manifest)
                attempt_number += 1
                continue

            if routed.get("status") == "FAILED" and routed.get("failureCode") == "PATCH_PLAN_ARTIFACT_MISSING":
                return self.runtime_summary(
                    progress,
                    "Workflow stopped because the Planning Agent did not provide a patch-plan artifact.",
                )

            # Unknown non-terminal failure after patch execution consumes the
            # remediation attempt and moves to the next bounded retry.
            attempt_number += 1

        max_attempts_result = self.handle_max_attempts_reached()
        self._record(progress, "max_attempts_routing", max_attempts_result)
        return self.runtime_summary(progress, "Workflow reached the configured remediation-attempt limit.")

    def replay_accepted_patch_set(self, attempt_number: int, attempt_workspace: str | None) -> dict:
        """Replay only validated accepted patch IDs onto the clean attempt workspace."""
        if not attempt_workspace:
            return {"status": "FAILED", "failureCode": "ATTEMPT_WORKSPACE_MISSING", "replayResults": []}

        manifest = self.manifest_store.load()
        accepted = manifest.get("acceptedPatchSet", {})
        accepted_patch_ids = set(accepted.get("patchIds", []))
        if not self._has_accepted_patch_set(manifest) or not accepted_patch_ids:
            return {"status": "SUCCESS", "replayResults": [], "message": "No accepted patch set to replay."}

        replay_results: list[dict[str, Any]] = []
        for source_attempt in accepted.get("sourceAttempts", []):
            source_entry = self._find_attempt(manifest, int(source_attempt))
            patch_plan_ref = source_entry.get("patchPlan") if source_entry else None
            if not patch_plan_ref:
                replay_results.append({"status": "SKIPPED", "sourceAttempt": source_attempt, "reason": "Patch plan not found."})
                continue

            patch_plan_path = self._resolve_workspace_ref(patch_plan_ref)
            filtered_plan_path = self._write_accepted_patch_replay_plan(
                attempt_number=attempt_number,
                source_attempt=int(source_attempt),
                source_patch_plan_path=patch_plan_path,
                accepted_patch_ids=accepted_patch_ids,
            )
            replay_dir = self.workspace.root / f"attempt-{attempt_number}" / "accepted-patch-set-replay"
            replay_dir.mkdir(parents=True, exist_ok=True)
            proof_path = str(replay_dir / f"source-attempt-{source_attempt}-patch-application-proof.json")
            diff_path = str(replay_dir / f"source-attempt-{source_attempt}.diff")
            result = apply_patch_plan(attempt_number, attempt_workspace, str(filtered_plan_path), proof_path, diff_path)
            replay_results.append({
                "status": result.get("status"),
                "sourceAttempt": source_attempt,
                "patchPlan": self._relative_ref(str(filtered_plan_path)),
                "sourcePatchPlan": self._relative_ref(patch_plan_path),
                "acceptedPatchIds": sorted(accepted_patch_ids),
                "patchApplicationProof": self._relative_ref(proof_path),
                "diff": self._relative_ref(diff_path),
                "failureCode": result.get("failureCode"),
            })
            if result.get("status") != "SUCCESS":
                return {"status": "FAILED", "failureCode": "ACCEPTED_PATCH_SET_REPLAY_FAILED", "replayResults": replay_results}
        return {"status": "SUCCESS", "replayResults": replay_results}

    def _write_accepted_patch_replay_plan(
        self,
        attempt_number: int,
        source_attempt: int,
        source_patch_plan_path: str,
        accepted_patch_ids: set[str],
    ) -> Path:
        source_plan = self._read_json(source_patch_plan_path)
        filtered_decisions: list[dict[str, Any]] = []
        for decision in source_plan.get("vulnerabilityDecisions", []):
            accepted_patches = [
                patch for patch in decision.get("patches", [])
                if patch.get("patchId") in accepted_patch_ids
            ]
            if not accepted_patches:
                continue
            filtered_decision = dict(decision)
            filtered_decision["patches"] = accepted_patches
            filtered_decisions.append(filtered_decision)

        replay_plan = dict(source_plan)
        replay_plan["artifactId"] = f"accepted-patch-set-replay-plan-attempt-{attempt_number}-from-{source_attempt}"
        replay_plan["attemptNumber"] = attempt_number
        replay_plan["sourceAttemptNumber"] = source_attempt
        replay_plan["acceptedPatchIds"] = sorted(accepted_patch_ids)
        replay_plan["vulnerabilityDecisions"] = filtered_decisions
        replay_plan.setdefault("warnings", []).append(
            "Replay plan was filtered by the orchestrator to include only validated acceptedPatchSet.patchIds."
        )

        replay_dir = self.workspace.root / f"attempt-{attempt_number}" / "accepted-patch-set-replay"
        replay_dir.mkdir(parents=True, exist_ok=True)
        replay_plan_path = replay_dir / f"source-attempt-{source_attempt}-accepted-patch-plan.json"
        replay_plan_path.write_text(json.dumps(replay_plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return replay_plan_path
