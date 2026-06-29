from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ToolResult:
    tool_name: str
    tool_version: str
    operation: str
    status: str
    artifact_path: str | None = None
    failure_code: str | None = None
    capabilities: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def success(cls, tool_name: str, operation: str, artifact_path: str | None = None, **payload: Any) -> "ToolResult":
        return cls(tool_name=tool_name, tool_version="1.0.0", operation=operation, status="SUCCESS", artifact_path=artifact_path, payload=payload)

    @classmethod
    def failed(cls, tool_name: str, operation: str, failure_code: str, errors: list[str]) -> "ToolResult":
        return cls(tool_name=tool_name, tool_version="1.0.0", operation=operation, status="FAILED", failure_code=failure_code, errors=errors)
