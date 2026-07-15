from __future__ import annotations

from pathlib import Path


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_ALLOWED_SUFFIXES = {".py", ".md", ".json", ".yaml", ".yml", ".toml", ".txt", ".xml"}
_BLOCKED_NAMES = {
    ".env",
    "credentials.json",
    "secrets.json",
    "service-account.json",
}
_BLOCKED_PARTS = {".git", ".venv", "venv", "__pycache__", "secrets", "workspace"}
_MAX_FILE_BYTES = 