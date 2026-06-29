from __future__ import annotations

import json
from pathlib import Path

from oss_remediation_agent.contracts import ToolResult, common_artifact
from oss_remediation_agent.utils import run_command

TOOL = "ValidationTool"


def validate_attempt(
    attempt_number: int,
    repository_path: str,
    patch_plan_path: str,
    patch_application_proof_path: str,
    output_path: str,
    artifact_output_dir: str,
    commands: dict | None = None,
    workflow_id: str = "unknown",
) -> dict:
    commands = commands or {"build": ["mvn", "clean", "install"], "test": ["mvn", "test"]}
    proof = json.loads(Path(patch_application_proof_path).read_text(encoding="utf-8"))
    changed_files = proof.get("filesChanged", [])
    scope_ok = all(Path(file_name).name == "pom.xml" for file_name in changed_files)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if not scope_ok:
        artifact = _artifact(attempt_number, workflow_id, "FAILED", patch_application_proof_path, changed_files, failed_stage="CHANGE_SCOPE_VALIDATION", failure="Only pom.xml changes are allowed")
        Path(output_path).write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return ToolResult(tool_name=TOOL, tool_version="1.0.0", operation="validate_attempt", status="FAILED", artifact_path=output_path, failure_code="CHANGE_SCOPE_FAILURE", payload={"changedFiles": changed_files}).to_dict()

    build_log = str(Path(artifact_output_dir) / "build.log")
    build = run_command(commands["build"], cwd=repository_path)
    Path(build_log).parent.mkdir(parents=True, exist_ok=True)
    Path(build_log).write_text((build.get("stdout") or "") + "\n" + (build.get("stderr") or ""), encoding="utf-8")

    if build["exitCode"] != 0:
        artifact = _artifact(attempt_number, workflow_id, "FAILED", patch_application_proof_path, changed_files, failed_stage="BUILD_VALIDATION", failure="Maven build failed", build_log=build_log, build_exit=build["exitCode"])
        Path(output_path).write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return ToolResult(tool_name=TOOL, tool_version="1.0.0", operation="validate_attempt", status="FAILED", artifact_path=output_path, failure_code="BUILD_FAILURE", payload={"buildLog": build_log}).to_dict()

    artifact = _artifact(attempt_number, workflow_id, "SUCCESS", patch_application_proof_path, changed_files, build_log=build_log, build_exit=0)
    Path(output_path).write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ToolResult(tool_name=TOOL, tool_version="1.0.0", operation="validate_attempt", status="SUCCESS", artifact_path=output_path, payload={"changeScopeValidation": "SUCCESS", "buildValidation": "SUCCESS"}).to_dict()


def _artifact(attempt_number, workflow_id, status, proof_path, changed_files, failed_stage=None, failure=None, build_log=None, build_exit=None):
    return common_artifact(
        artifact_id=f"validation-result-attempt-{attempt_number}",
        workflow_id=workflow_id,
        created_by=TOOL,
        status=status,
        attemptNumber=attempt_number,
        patchApplicationProof=proof_path,
        changeScopeValidation={"status": "FAILED" if failed_stage == "CHANGE_SCOPE_VALIDATION" else "SUCCESS", "onlyPomFilesChanged": all(Path(file_name).name == "pom.xml" for file_name in changed_files), "changedFiles": changed_files, "failureSummary": failure if failed_stage == "CHANGE_SCOPE_VALIDATION" else None},
        buildValidation={"status": "SUCCESS" if build_exit == 0 else ("FAILED" if build_exit is not None else "NOT_RUN"), "command": "mvn clean install", "exitCode": build_exit, "logFile": build_log},
        testValidation={"status": "NOT_RUN"},
        osvValidation={"status": "NOT_RUN"},
        summary={"failedStage": failed_stage, "failureSummary": failure},
        artifactReferences={"buildLog": build_log} if build_log else {},
        errors=[] if status == "SUCCESS" else [failure or "validation failed"],
        warnings=[],
    )
