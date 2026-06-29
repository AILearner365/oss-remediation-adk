from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ManifestStore:
    def __init__(self, manifest_path: str | Path):
        self.path = Path(manifest_path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, manifest: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
