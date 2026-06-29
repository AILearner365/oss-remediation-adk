from __future__ import annotations

import difflib
import json
from pathlib import Path

from oss_remediation_agent.contracts import ToolResult, common_artifact

TOOL = "GenericPatchApplyTool"


def _load_plan(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _iter_patches(plan: dict):
    for decision in plan.get("vulnerabilityDecisions", []):
        for patch in decision.get("patches", []):
            yield patch


def dry_run(attempt_number: int, repository_path: str, patch_plan_path: str, output_path: str) -> dict:
    plan = _load_plan(patch_plan_path)
    repo = Path(repository_path)
    results = []
    errors = []
    for patch in _iter_patches(plan):
        file_path = repo / patch["file"]
        count = file_path.read_text(encoding="utf-8").count(patch["oldText"]) if file_path.exists() else 0
        expected = patch.get("expectedOccurrences", 1)
        status = "READY" if count == expected else "FAILED"
        if status == "FAILED":
            errors.append(f"{patch['patchId']}: expected {expected} occurrence(s), found {count}")
        results.append({"patchId": patch["patchId"], "file": patch["file"], "status": status, "actualOccurrences": count})
    status = "FAILED" if errors else "SUCCESS"
    artifact = common_artifact(artifact_id=f"patch-dry-run-attempt-{attempt_number}", workflow_id=plan.get("workflowId", "unknown"), created_by=TOOL, status=status, attemptNumber=attempt_number, patchResults=results, errors=errors)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ToolResult(tool_name=TOOL, tool_version="1.0.0", operation="dry_run", status=status, artifact_path=output_path, failure_code="PATCH_DRY_RUN_FAILED" if errors else None, payload={"patchesRequested": len(results)}, errors=errors).to_dict()


def apply(attempt_number: int, repository_path: str, patch_plan_path: str, output_path: str, diff_file: str) -> dict:
    plan = _load_plan(patch_plan_path)
    repo = Path(repository_path)
    results = []
    errors = []
    diff_lines = []
    changed = []
    for patch in _iter_patches(plan):
        file_path = repo / patch["file"]
        if not file_path.exists():
            errors.append(f"{patch['patchId']}: file not found")
            results.append({"patchId": patch["patchId"], "file": patch["file"], "status": "FAILED"})
            continue
        before = file_path.read_text(encoding="utf-8")
        count = before.count(patch["oldText"])
        expected = patch.get("expectedOccurrences", 1)
        if count != expected:
            errors.append(f"{patch['patchId']}: expected {expected} occurrence(s), found {count}")
            results.append({"patchId": patch["patchId"], "file": patch["file"], "status": "FAILED", "actualOccurrences": count})
            continue
        after = before.replace(patch["oldText"], patch["newText"], 1)
        file_path.write_text(after, encoding="utf-8")
        changed.append(patch["file"])
        diff_lines.extend(difflib.unified_diff(before.splitlines(), after.splitlines(), fromfile=f"a/{patch['file']}", tofile=f"b/{patch['file']}", lineterm=""))
        results.append({"patchId": patch["patchId"], "file": patch["file"], "status": "APPLIED", "expectedOccurrences": expected, "actualOccurrences": count, "oldTextMatched": True})
    Path(diff_file).parent.mkdir(parents=True, exist_ok=True)
    Path(diff_file).write_text("\n".join(diff_lines) + ("\n" if diff_lines else ""), encoding="utf-8")
    status = "FAILED" if errors else "SUCCESS"
    artifact = common_artifact(artifact_id=f"patch-application-proof-attempt-{attempt_number}", workflow_id=plan.get("workflowId", "unknown"), created_by=TOOL, status=status, attemptNumber=attempt_number, planId=plan.get("planId"), patchesRequested=len(results), patchesApplied=len([r for r in results if r["status"] == "APPLIED"]), filesChanged=sorted(set(changed)), patchResults=results, artifactReferences={"diffFile": diff_file}, errors=errors)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ToolResult(tool_name=TOOL, tool_version="1.0.0", operation="apply", status=status, artifact_path=output_path, failure_code="PATCH_APPLY_FAILED" if errors else None, payload={"filesChanged": sorted(set(changed)), "diffFile": diff_file}, errors=errors).to_dict()
