from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_REPOSITORY_ROOT = Path(
    os.getenv("OSS_REPO_ROOT", str(_DEFAULT_REPOSITORY_ROOT))
).expanduser().resolve()

_ALLOWED_SUFFIXES = {
    ".py",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".txt",
    ".xml",
}
_BLOCKED_NAMES = {
    ".env",
    "credentials.json",
    "secrets.json",
    "service-account