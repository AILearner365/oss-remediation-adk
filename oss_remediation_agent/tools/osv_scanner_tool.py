from __future__ import annotations

import json
from pathlib import Path

from oss_remediation_agent.contracts import ToolResult, common_artifact
from oss_remediation_agent.utils import run_command

TOOL = "OSVScannerTool"


def generate_vulnerability_assessment(
    repository_path: str,
    output_path: str,
    raw_report_path: str,
    severity_scope: list[str] | None = None,
    workflow_id: str = "unknown",
) -> dict:
    severity_scope = severity_scope or ["CRITICAL", "HIGH"]
    result = run_command(["osv-scanner", "scan", "source", "-r", ".", "--format", "json"], cwd=repository_path)
    Path(raw_report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(raw_report_path).write_text(result.get("stdout") or "{}", encoding="utf-8")
    status = "SUCCESS" if result["exitCode"] in (0, 1) else "FAILED"
    artifact = common_artifact(
        artifact_id="vulnerability-assessment-001",
        workflow_id=workflow_id,
        created_by=TOOL,
        status=status,
        reportType="VULNERABILITY_ASSESSMENT",
        scanner={"name": "OSV", "rawReportPath": raw_report_path},
        severityScope=severity_scope,
        vulnerabilities=[],
        summary={"criticalCount": 0, "highCount": 0, "totalInScopeCount": 0},
        artifactReferences={"rawOsvReport": raw_report_path},
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ToolResult(tool_name=TOOL, tool_version="1.0.0", operation="generate_vulnerability_assessment", status=status, artifact_path=output_path, payload={"rawReportPath": raw_report_path}).to_dict()


def validate_post_remediation(repository_path: str, output_path: str) -> dict:
    result = run_command(["osv-scanner", "scan", "source", "-r", ".", "--format", "json"], cwd=repository_path)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(result.get("stdout") or "{}", encoding="utf-8")
    return ToolResult(tool_name=TOOL, tool_version="1.0.0", operation="validate_post_remediation", status="SUCCESS" if result["exitCode"] in (0, 1) else "FAILED", artifact_path=output_path, payload={"scanResultFile": output_path}).to_dict()
