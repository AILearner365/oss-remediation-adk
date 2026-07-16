from __future__ import annotations

import json
import os
import signal
import subprocess
from pathlib import Path

from oss_remediation_agent.contracts import ToolResult, common_artifact
from oss_remediation_agent.utils import run_command

TOOL = "BaselineBuildTool"
SPRING_BOOT_RUN_STARTUP_WINDOW_SECONDS = 30


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


def run_spring_boot_startup_check(
    repository_path: str,
    command: list[str] | None = None,
    output_path: str = "spring-boot-run-result.json",
    log_file: str = "spring-boot-run.log",
    workflow_id: str = "unknown",
    startup_window_seconds: int = SPRING_BOOT_RUN_STARTUP_WINDOW_SECONDS,
    artifact_id: str = "spring-boot-run-result-001",
    tool_name: str = TOOL,
    operation: str = "run_spring_boot_startup_check",
) -> dict:
    """Run the shared POC Spring Boot startup smoke check.

    A successful ``mvn spring-boot:run`` process stays alive. For this initial
    POC, the check passes when it remains alive for the fixed startup window;
    it is then terminated so Stage 1 does not leave an application running.

    TODO: make the Maven module, readiness strategy, timeout, and environment
    inputs configurable before treating this as a production readiness check.
    """
    command = command or ["mvn", "spring-boot:run"]
    process: subprocess.Popen[str] | None = None
    stdout = ""
    exit_code: int | None = None
    failure_code: str | None = None
    status = "FAILED"

    try:
        process = subprocess.Popen(
            command,
            cwd=repository_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=os.name != "nt",
        )
        try:
            stdout, _ = process.communicate(timeout=startup_window_seconds)
            exit_code = process.returncode
            failure_code = "SPRING_BOOT_RUN_EXITED_EARLY"
        except subprocess.TimeoutExpired as exc:
            stdout = _as_text(exc.stdout)
            _terminate_process(process)
            tail, _ = process.communicate(timeout=10)
            stdout += _as_text(tail)
            exit_code = process.returncode
            status = "SUCCESS"
    except FileNotFoundError as exc:
        stdout = str(exc)
        exit_code = 127
        failure_code = "SPRING_BOOT_RUN_COMMAND_NOT_FOUND"
    except subprocess.TimeoutExpired:
        _terminate_process(process)
        if process is not None:
            tail, _ = process.communicate()
            stdout += _as_text(tail)
            exit_code = process.returncode
        failure_code = "SPRING_BOOT_RUN_TERMINATION_TIMEOUT"
    except Exception as exc:
        _terminate_process(process)
        if process is not None:
            tail, _ = process.communicate()
            stdout += _as_text(tail)
            exit_code = process.returncode
        stdout += f"\n{exc}"
        failure_code = "SPRING_BOOT_RUN_FAILED"

    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    Path(log_file).write_text(stdout, encoding="utf-8")
    failure_summary = _maven_failure_summary(stdout) if status != "SUCCESS" else None
    artifact = common_artifact(
        artifact_id=artifact_id,
        workflow_id=workflow_id,
        created_by=tool_name,
        status=status,
        command=" ".join(command),
        exitCode=exit_code,
        startupWindowSeconds=startup_window_seconds,
        startupCriterion="Process remained running for the configured POC startup window.",
        logFile=log_file,
        logExcerpt=stdout[-2000:],
        artifactReferences={"springBootRunLog": log_file},
        failureSummary=failure_summary,
        errors=[] if status == "SUCCESS" else [failure_code or "SPRING_BOOT_RUN_FAILED"],
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ToolResult(
        tool_name=tool_name,
        tool_version="1.0.0",
        operation=operation,
        status=status,
        artifact_path=output_path,
        failure_code=failure_code,
        payload={
            "exitCode": exit_code,
            "logFile": log_file,
            "startupWindowSeconds": startup_window_seconds,
            "failureSummary": failure_summary,
        },
        errors=[] if status == "SUCCESS" else [failure_code or "SPRING_BOOT_RUN_FAILED"],
    ).to_dict()


def run_baseline_spring_boot(
    repository_path: str,
    command: list[str] | None = None,
    output_path: str = "baseline/spring-boot-run-result.json",
    log_file: str = "baseline/spring-boot-run.log",
    workflow_id: str = "unknown",
    startup_window_seconds: int = SPRING_BOOT_RUN_STARTUP_WINDOW_SECONDS,
) -> dict:
    """Run the shared POC startup check for Stage 1 baseline preparation."""
    return run_spring_boot_startup_check(
        repository_path=repository_path,
        command=command,
        output_path=output_path,
        log_file=log_file,
        workflow_id=workflow_id,
        startup_window_seconds=startup_window_seconds,
        artifact_id="baseline-spring-boot-run-result-001",
        operation="run_baseline_spring_boot",
    )


def _terminate_process(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGTERM)
        else:  # pragma: no cover - platform dependent
            process.terminate()
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGKILL)
        else:  # pragma: no cover - platform dependent
            process.kill()


def _as_text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def _maven_failure_summary(log_output: str) -> str | None:
    """Extract Maven's actionable error and omit its non-actionable help suffix."""
    for line in log_output.splitlines():
        normalized = line.strip()
        if "Failed to execute goal" not in normalized:
            continue
        if normalized.startswith("[ERROR]"):
            normalized = normalized[len("[ERROR]"):].strip()
        return normalized.split(" -> [Help", 1)[0].strip()
    return None
