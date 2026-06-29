from __future__ import annotations

import json
from pathlib import Path

COMMON_REQUIRED = ["schemaVersion", "artifactId", "workflowId", "createdBy", "status"]


def validate_common_artifact(data: dict) -> list[str]:
    errors = []
    for field in COMMON_REQUIRED:
        if field not in data:
            errors.append(f"Missing required field: {field}")
    if data.get("errors") is not None and not isinstance(data.get("errors"), list):
        errors.append("errors must be a list")
    if data.get("warnings") is not None and not isinstance(data.get("warnings"), list):
        errors.append("warnings must be a list")
    return errors


def validate_tool_result(data: dict) -> list[str]:
    required = ["toolName", "toolVersion", "operation", "status", "errors", "warnings"]
    errors = [f"Missing required field: {field}" for field in required if field not in data]
    if data.get("payload") is not None and not isinstance(data.get("payload"), dict):
        errors.append("payload must be an object")
    return errors


def validate_artifact_file(path: str | Path) -> list[str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_common_artifact(data)
