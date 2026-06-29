from __future__ import annotations

import json
from pathlib import Path

from oss_remediation_agent.contracts import ToolResult, common_artifact
from oss_remediation_agent.utils import run_command

TOOL = "BaselineBuildTool"


def run_baseline_build(
    repository_path: str,
    command: list[str] | None = None,
    output_path: str = "baseline/baseline-build-result.json",
    log_file: str = "baseline/baseline-build.log",
    workflow_id: str = "unknown",
) -> dict:
    command = command or ["mvn", "clean", "install"]
    result = run_command(command, cwd=repository_path)
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    Path(log_file).write_text((result.get("stdout") or "") + "\n" + (result.get("stderr") or ""), encoding="utf-8")
    status = "SUCCESS" if result["exitCode"] == 0 else "FAILED"
    artifact = common_artifact(
        artifact_id="baseline-build-result-001",
        workflow_id=workflow_id,
        created_by=TOOL,
        status=status,
        command=" ".join(command),
        exitCode=result["exitCode"],
        logFile=log_file,
        logExcerpt=((result.get("stdout") or result.get("stderr") or "")[-2000:]),
        artifactReferences={"buildLog": log_file},
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ToolResult(
        tool_name=TOOL,
        tool_version="1.0.0",
        operation="run_baseline_build",
        status=status,
        artifact_path=output_path,
        failure_code=None if status == "SUCCESS" else "BASELINE_BUILD_FAILED",
        payload={"exitCode": result["exitCode"], "logFile": log_file},
    ).to_dict()
