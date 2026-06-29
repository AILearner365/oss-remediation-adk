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


def _validate_patches(repo: Path, patches: list[dict]) -> tuple[list[dict], list[str], dict[Path, str]]:
    results = []
    errors = []
    file_contents: dict[Path, str] = {}
    for patch in patches:
        file_path = repo / patch["file"]
        expected = patch.get("expectedOccurrences", 1)
        if file_path.name != "pom.xml":
            errors.append(f"{patch['patchId']}: unsupported file type")
            results.append({"patchId": patch["patchId"], "file": patch["file"], "status": "FAILED", "error": "unsupported file type"})
            continue
        if not file_path.exists():
            errors.append(f"{patch['patchId']}: file not found")
            results.append({"patchId": patch["patchId"], "file": patch["file"], "status": "FAILED", "error": "file not found"})
            continue
        before = file_contents.get(file_path)
        if before is None:
            before = file_path.read_text(encoding="utf-8")
            file_contents[file_path] = before
        count = before.count(patch["oldText"])
        status = "READY" if count == expected else "FAILED"
        if status == "FAILED":
            errors.append(f"{patch['patchId']}: expected {expected} occurrence(s), found {count}")
        results.append({"patchId": patch["patchId"], "file": patch["file"], "status": status, "expectedOccurrences": expected, "actualOccurrences": count})
    return results, errors, file_contents


def dry_run(attempt_number: int, repository_path: str, patch_plan_path: str, output_path: str) -> dict:
    plan = _load_plan(patch_plan_path)
    repo = Path(repository_path)
    patches = list(_iter_patches(plan))
    results, errors, _ = _validate_patches(repo, patches)
    status = "FAILED" if errors else "SUCCESS"
    artifact = common_artifact(
        artifact_id=f"patch-dry-run-attempt-{attempt_number}",
        workflow_id=plan.get("workflowId", "unknown"),
        created_by=TOOL,
        status=status,
        attemptNumber=attempt_number,
        patchResults=results,
        errors=errors,
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ToolResult(tool_name=TOOL, tool_version="1.0.0", operation="dry_run", status=status, artifact_path=output_path, failure_code="PATCH_DRY_RUN_FAILED" if errors else None, payload={"patchesRequested": len(results)}, errors=errors).to_dict()


def apply(attempt_number: int, repository_path: str, patch_plan_path: str, output_path: str, diff_file: str) -> dict:
    plan = _load_plan(patch_plan_path)
    repo = Path(repository_path)
    patches = list(_iter_patches(plan))
    validation_results, errors, file_contents = _validate_patches(repo, patches)

    if errors:
        Path(diff_file).parent.mkdir(parents=True, exist_ok=True)
        Path(diff_file).write_text("", encoding="utf-8")
        artifact = common_artifact(
            artifact_id=f"patch-application-proof-attempt-{attempt_number}",
            workflow_id=plan.get("workflowId", "unknown"),
            created_by=TOOL,
            status="FAILED",
            attemptNumber=attempt_number,
            planId=plan.get("planId"),
            patchesRequested=len(validation_results),
            patchesApplied=0,
            filesChanged=[],
            patchResults=validation_results,
            artifactReferences={"diffFile": diff_file},
            errors=errors,
        )
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return ToolResult(tool_name=TOOL, tool_version="1.0.0", operation="apply", status="FAILED", artifact_path=output_path, failure_code="PATCH_APPLY_FAILED", payload={"filesChanged": [], "diffFile": diff_file}, errors=errors).to_dict()

    # Build all target file contents in memory first so apply remains atomic.
    updated_contents = dict(file_contents)
    patch_results = []
    for patch in patches:
        file_path = repo / patch["file"]
        before_for_patch = updated_contents[file_path]
        expected = patch.get("expectedOccurrences", 1)
        updated_contents[file_path] = before_for_patch.replace(patch["oldText"], patch["newText"], expected)
        patch_results.append({
            "patchId": patch["patchId"],
            "file": patch["file"],
            "status": "APPLIED",
            "expectedOccurrences": expected,
            "actualOccurrences": file_contents[file_path].count(patch["oldText"]),
            "oldTextMatched": True,
        })

    diff_lines = []
    files_changed = []
    for file_path, before in file_contents.items():
        after = updated_contents[file_path]
        if before == after:
            continue
        file_path.write_text(after, encoding="utf-8")
        relative = str(file_path.relative_to(repo))
        files_changed.append(relative)
        diff_lines.extend(difflib.unified_diff(before.splitlines(), after.splitlines(), fromfile=f"a/{relative}", tofile=f"b/{relative}", lineterm=""))

    Path(diff_file).parent.mkdir(parents=True, exist_ok=True)
    Path(diff_file).write_text("\n".join(diff_lines) + ("\n" if diff_lines else ""), encoding="utf-8")
    files_changed = sorted(set(files_changed))
    artifact = common_artifact(
        artifact_id=f"patch-application-proof-attempt-{attempt_number}",
        workflow_id=plan.get("workflowId", "unknown"),
        created_by=TOOL,
        status="SUCCESS",
        attemptNumber=attempt_number,
        planId=plan.get("planId"),
        patchesRequested=len(patch_results),
        patchesApplied=len(patch_results),
        filesChanged=files_changed,
        patchResults=patch_results,
        artifactReferences={"diffFile": diff_file},
        errors=[],
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ToolResult(tool_name=TOOL, tool_version="1.0.0", operation="apply", status="SUCCESS", artifact_path=output_path, payload={"filesChanged": files_changed, "diffFile": diff_file}).to_dict()
