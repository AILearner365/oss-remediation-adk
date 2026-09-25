from __future__ import annotations

from pathlib import Path
from typing import Iterable


EVIDENCE_EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        ".gradle",
        ".m2",
        ".m2_repo",
        "node_modules",
        "target",
    }
)


def is_generated_evidence_path(path: str | Path) -> bool:
    return any(part in EVIDENCE_EXCLUDED_DIRECTORIES for part in Path(path).parts)


def scanner_copy_ignore(_directory: str, names: Iterable[str]) -> set[str]:
    return set(names) & EVIDENCE_EXCLUDED_DIRECTORIES
