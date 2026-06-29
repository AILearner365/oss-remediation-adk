from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def contract_name(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


@dataclass
class Artifact:
    artifact_id: str
    workflow_id: str
    created_by: str
    status: str
    schema_version: str = "1.0"
    created_at: str = field(default_factory=now_utc)
    policy: dict[str, Any] = field(default_factory=dict)
    artifact_references: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {contract_name(item.name): getattr(self, item.name) for item in fields(self)}

    def write_json(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @classmethod
    def read_json(cls, path: str | Path) -> dict[str, Any]:
        return json.loads(Path(path).read_text(encoding="utf-8"))


def common_artifact(artifact_id: str, workflow_id: str, created_by: str, status: str, **extra: Any) -> dict[str, Any]:
    data = Artifact(artifact_id=artifact_id, workflow_id=workflow_id, created_by=created_by, status=status).to_dict()
    data.update(extra)
    return data
