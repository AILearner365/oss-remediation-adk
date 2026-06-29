from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


class WorkspaceManager:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def initialize(self) -> None:
        for directory in ("baseline", "final"):
            (self.root / directory).mkdir(parents=True, exist_ok=True)

    def attempt_dir(self, attempt_number: int) -> Path:
        path = self.root / f"attempt-{attempt_number}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_json(self, relative_path: str, data: dict[str, Any]) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def read_json(self, relative_path: str) -> dict[str, Any]:
        return json.loads((self.root / relative_path).read_text(encoding="utf-8"))

    def copy_baseline_to_attempt(self, attempt_number: int, baseline_repo: str = "baseline/repository") -> Path:
        source = self.root / baseline_repo
        target = self.attempt_dir(attempt_number) / "repository"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
        return target
