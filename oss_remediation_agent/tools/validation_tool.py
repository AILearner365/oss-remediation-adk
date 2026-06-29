from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from oss_remediation_agent.contracts import ToolResult, common_artifact
from oss_remediation_agent.tools.osv_scanner_tool import validate_post_remediation
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
    severity_scope: list[str] | None = None,
    baseline_assessment_path: str | None = None,
) -> dict:
    commands = commands or {
        "build": ["mvn", "clean", "install"],
        "test": ["mvn", "test"],
    }
    severity_scope = severity_scope or ["CRITICAL", "HIGH"]
    proof = json.loads(Path(patch_application_proof_path).read_text(encoding="utf-8"))
    changed_files = proof.get("filesChanged", [])
    scope = _change_scope(repository_path, changed_files, patch_plan_path)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if scope["status"] != "SUCCESS":
        artifact = _artifact(
            attempt_number,
            workflow_id,
            "FAILED",
            patch_application_proof_path,
            scope,
            failed_stage="CHANGE_SCOPE_VALIDATION",
            failure=scope["failureSummary"],
        )
        _write(output_path, artifact)
        return ToolResult(tool_name=TOOL, tool_version="1.0.0", operation="validate_attempt", status="FAILED", artifact_path=output_path, failure_code="CHANGE_SCOPE_FAILURE", payload={"changedFiles": changed_files}).to_dict()

    build_log = str(Path(artifact_output_dir) / "build.log")
    build = _run_and_log(commands["build"], repository_path, build_log)
    if build["exitCode"] != 0:
        artifact = _artifact(attempt_number, workflow_id, "FAILED", patch_application_proof_path, scope, failed_stage="BUILD_VALIDATION", failure="Maven build failed", build_log=build_log, build_exit=build["exitCode"])
        _write(output_path, artifact)
        return ToolResult(tool_name=TOOL, tool_version="1.0.0", operation="validate_attempt", status="FAILED", artifact_path=output_path, failure_code="BUILD_FAILURE", payload={"buildLog": build_log}).to_dict()

    test_log = str(Path(artifact_output_dir) / "test.log")
    test = _run_and_log(commands["test"], repository_path, test_log)
    if test["exitCode"] != 0:
        artifact = _artifact(attempt_number, workflow_id, "FAILED", patch_application_proof_path, scope, failed_stage="TEST_VALIDATION", failure="Maven tests failed", build_log=build_log, build_exit=0, test_log=test_log, test_exit=test["exitCode"])
        _write(output_path, artifact)
        return ToolResult(tool_name=TOOL, tool_version="1.0.0", operation="validate_attempt", status="FAILED", artifact_path=output_path, failure_code="TEST_FAILURE", payload={"testLog": test_log}).to_dict()

    osv_report = str(Path(artifact_output_dir) / "osv-report.json")
    osv = validate_post_remediation(repository_path, osv_report, severity_scope)
    remaining = osv.get("payload", {}).get("remainingVulnerabilities", [])
    remaining_critical = int(osv.get("payload", {}).get("remainingCriticalCount") or 0)
    remaining_high = int(osv.get("payload", {}).get("remainingHighCount") or 0)
    new_introduced = _new_vulnerabilities_introduced(baseline_assessment_path, remaining)
    osv_status = "SUCCESS" if osv["status"] == "SUCCESS" else "FAILED"

    artifact_status = "SUCCESS" if osv_status == "SUCCESS" and not new_introduced else "FAILED"
    failure = None
    if osv_status != "SUCCESS":
        failure = "OSV scan failed"
    elif new_introduced:
        failure = "New Critical or High vulnerability introduced"

    artifact = _artifact(
        attempt_number,
        workflow_id,
        artifact_status,
        patch_application_proof_path,
        scope,
        failed_stage=None if artifact_status == "SUCCESS" else "OSV_VALIDATION",
        failure=failure,
        build_log=build_log,
        build_exit=0,
        test_log=test_log,
        test_exit=0,
        osv_report=osv_report,
        remaining_critical=remaining_critical,
        remaining_high=remaining_high,
        remaining_vulnerabilities=remaining,
        new_introduced=new_introduced,
        osv_status=osv_status,
    )
    _write(output_path, artifact)
    return ToolResult(
        tool_name=TOOL,
        tool_version="1.0.0",
        operation="validate_attempt",
        status=artifact_status,
        artifact_path=output_path,
        failure_code=None if artifact_status == "SUCCESS" else "OSV_VALIDATION_FAILURE",
        payload={
            "changeScopeValidation": scope["status"],
            "buildValidation": "SUCCESS",
            "testValidation": "SUCCESS",
            "osvValidation": osv_status,
            "remainingCriticalCount": remaining_critical,
            "remainingHighCount": remaining_high,
            "newCriticalHighIntroduced": new_introduced,
        },
    ).to_dict()


def _change_scope(repository_path: str, changed_files: list[str], patch_plan_path: str) -> dict:
    repo = Path(repository_path)
    git_files_result = run_command(["git", "diff", "--name-only"], cwd=repo, timeout=300)
    actual_files = [line.strip() for line in (git_files_result.get("stdout") or "").splitlines() if line.strip()]
    if not actual_files:
        actual_files = changed_files
    diff_result = run_command(["git", "diff", "--unified=0"], cwd=repo, timeout=300)
    diff_text = (diff_result.get("stdout") or "")
    expected_files = _expected_patch_files(patch_plan_path)
    only_pom = all(Path(file_name).name == "pom.xml" for file_name in actual_files)
    no_source = not any(file_name.startswith("src/") for file_name in actual_files)
    only_intended_files = set(actual_files).issubset(expected_files) if expected_files else only_pom
    no_jdk = not any(token in diff_text for token in ["java.version", "maven.compiler.source", "maven.compiler.target", "maven.compiler.release"])
    no_plugin = "<plugin" not in diff_text and "<plugins" not in diff_text
    no_workaround = not any(token.lower() in diff_text.lower() for token in ["ignore", "suppress", "exception"])
    no_formatting_rewrite = _looks_like_small_targeted_diff(diff_text, actual_files)
    ok = all([only_pom, no_source, only_intended_files, no_jdk, no_plugin, no_workaround, no_formatting_rewrite])
    failure = None if ok else "Change scope validation failed"
    return {
        "status": "SUCCESS" if ok else "FAILED",
        "onlyPomFilesChanged": only_pom,
        "noSourceCodeChanges": no_source,
        "noPomFormattingRewrite": no_formatting_rewrite,
        "onlyIntendedDependencyVersionChanges": only_intended_files,
        "noSuppressionOrIgnoreAdded": no_workaround,
        "noJdkVersionChange": no_jdk,
        "noPluginBuildLogicChange": no_plugin,
        "changedFiles": actual_files,
        "failureSummary": failure,
    }


def _expected_patch_files(patch_plan_path: str) -> set[str]:
    try:
        plan = json.loads(Path(patch_plan_path).read_text(encoding="utf-8"))
    except Exception:
        return set()
    files = set()
    for decision in plan.get("vulnerabilityDecisions", []):
        for patch in decision.get("patches", []):
            files.add(patch.get("file"))
    return {file_name for file_name in files if file_name}


def _looks_like_small_targeted_diff(diff_text: str, actual_files: list[str]) -> bool:
    if not diff_text:
        return True
    changed_lines = [line for line in diff_text.splitlines() if line.startswith("+") or line.startswith("-")]
    changed_lines = [line for line in changed_lines if not line.startswith("+++") and not line.startswith("---")]
    return len(changed_lines) <= max(20, len(actual_files) * 12)


def _new_vulnerabilities_introduced(baseline_assessment_path: str | None, remaining: list[dict[str, Any]]) -> bool:
    if not baseline_assessment_path or not Path(baseline_assessment_path).exists():
        return False
    try:
        baseline = json.loads(Path(baseline_assessment_path).read_text(encoding="utf-8"))
    except Exception:
        return False
    baseline_keys = {_vuln_key(item) for item in baseline.get("vulnerabilities", [])}
    return any(_vuln_key(item) not in baseline_keys for item in remaining)


def _vuln_key(item: dict[str, Any]) -> tuple:
    dependency = item.get("dependency") or {}
    return (
        item.get("vulnerabilityId"),
        dependency.get("packageName") or f"{dependency.get('groupId')}:{dependency.get('artifactId')}",
        dependency.get("currentVersion"),
    )


def _run_and_log(command: list[str], cwd: str, log_file: str) -> dict:
    result = run_command(command, cwd=cwd)
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    Path(log_file).write_text((result.get("stdout") or "") + "\n" + (result.get("stderr") or ""), encoding="utf-8")
    return result


def _artifact(attempt_number, workflow_id, status, proof_path, scope, failed_stage=None, failure=None, build_log=None, build_exit=None, test_log=None, test_exit=None, osv_report=None, remaining_critical=None, remaining_high=None, remaining_vulnerabilities=None, new_introduced=False, osv_status="NOT_RUN"):
    refs = {}
    if build_log:
        refs["buildLog"] = build_log
    if test_log:
        refs["testLog"] = test_log
    if osv_report:
        refs["osvReport"] = osv_report
    return common_artifact(
        artifact_id=f"validation-result-attempt-{attempt_number}",
        workflow_id=workflow_id,
        created_by=TOOL,
        status=status,
        attemptNumber=attempt_number,
        patchApplicationProof=proof_path,
        changeScopeValidation=scope,
        buildValidation={"status": "SUCCESS" if build_exit == 0 else ("FAILED" if build_exit is not None else "NOT_RUN"), "command": "mvn clean install", "exitCode": build_exit, "logFile": build_log},
        testValidation={"status": "SUCCESS" if test_exit == 0 else ("FAILED" if test_exit is not None else "NOT_RUN"), "command": "mvn test", "exitCode": test_exit, "logFile": test_log},
        osvValidation={"status": osv_status, "scanResultFile": osv_report, "remainingCriticalCount": remaining_critical, "remainingHighCount": remaining_high, "newCriticalHighIntroduced": new_introduced, "remainingVulnerabilities": remaining_vulnerabilities or []},
        summary={"failedStage": failed_stage, "failureSummary": failure},
        artifactReferences=refs,
        errors=[] if status == "SUCCESS" else [failure or "validation failed"],
        warnings=[],
    )


def _write(path: str, data: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
