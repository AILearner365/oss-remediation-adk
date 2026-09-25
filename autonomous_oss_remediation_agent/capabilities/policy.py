from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from ..config import RuntimePolicy


@dataclass(frozen=True)
class RuntimeBoundaryResult:
    approved: bool
    reason: str


def evaluate_runtime_boundary(policy: RuntimePolicy) -> RuntimeBoundaryResult:
    if not policy.trusted_repository:
        return RuntimeBoundaryResult(False, "trusted_repository must be explicitly approved")
    if not policy.dedicated_runner:
        return RuntimeBoundaryResult(False, "dedicated_runner must be explicitly approved")
    if not policy.enable_autonomous_shell:
        return RuntimeBoundaryResult(False, "autonomous shell capability is disabled")
    return RuntimeBoundaryResult(
        True,
        "trusted repository and dedicated runner assumptions explicitly approved; no hard shell containment is claimed",
    )


class CommandPolicy:
    _BLOCKED_PATTERNS = (
        (re.compile(r"(^|[;&|]\s*)sudo(?:\s|$)", re.IGNORECASE), "privilege elevation is prohibited"),
        (re.compile(r"(^|[;&|]\s*)runas(?:\.exe)?(?:\s|$)", re.IGNORECASE), "privilege elevation is prohibited"),
        (re.compile(r"\bgit\s+push\b", re.IGNORECASE), "delivery operations are deterministic-only"),
        (re.compile(r"\bgh(?:\.exe)?\s+", re.IGNORECASE), "credentialed GitHub tools are not exposed to the agent"),
        (re.compile(r"\bgit\s+credential(?:-manager(?:-core)?)?\b", re.IGNORECASE), "credential access is prohibited"),
        (re.compile(r"\bcredential-manager(?:-core)?(?:\.exe)?\b", re.IGNORECASE), "credential access is prohibited"),
        (re.compile(r"\b(?:sc|shutdown|setx|reg)(?:\.exe)?\s+", re.IGNORECASE), "machine-wide configuration is prohibited"),
        (re.compile(r"\bnet(?:\.exe)?\s+(?:user|localgroup|accounts)\b", re.IGNORECASE), "account configuration is prohibited"),
        (re.compile(r"\b(?:winget|choco)(?:\.exe)?\s+install\b", re.IGNORECASE), "global package installation is prohibited"),
        (re.compile(r"\bpip(?:3)?\s+install\s+[^\r\n]*(?:--user|--prefix|--root)\b", re.IGNORECASE), "non-workspace package installation is prohibited"),
        (re.compile(r"\bnpm\s+(?:install|i)\s+(?:--global|-g)\b", re.IGNORECASE), "global package installation is prohibited"),
        (re.compile(r"\bdocker(?:\.exe)?\s+", re.IGNORECASE), "container control is outside the approved agent boundary"),
    )

    def evaluate(self, command: str) -> tuple[bool, str | None]:
        for pattern, reason in self._BLOCKED_PATTERNS:
            if pattern.search(command):
                return False, reason
        return True, None


def sanitized_agent_environment(
    run_root: Path,
    allow_network: bool,
    runtime: Path | None = None,
) -> dict[str, str]:
    preserved = {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "JAVA_HOME",
        "LANG",
        "LC_ALL",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
    }
    environment = {name: value for name, value in os.environ.items() if name.upper() in preserved}
    runtime_root = runtime or run_root / "temp" / "agent-runtime"
    home = runtime_root / "home"
    temp = runtime_root / "temp"
    maven_user_home = home / ".m2"
    for directory in (home, temp, maven_user_home / "repository"):
        directory.mkdir(parents=True, exist_ok=True)
    environment.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "TEMP": str(temp),
            "TMP": str(temp),
            "TMPDIR": str(temp),
            "MAVEN_USER_HOME": str(maven_user_home),
            "MAVEN_OPTS": _maven_opts(
                environment.get("MAVEN_OPTS", ""), maven_user_home / "repository"
            ),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "NUL" if os.name == "nt" else "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "Never",
            "AUTONOMOUS_OSS_NETWORK_MODE": "approved" if allow_network else "disabled-by-policy",
        }
    )
    return environment


def isolated_runtime_environment(base: dict[str, str], runtime: Path) -> dict[str, str]:
    environment = dict(base)
    home = runtime / "home"
    temp = runtime / "temp"
    maven_user_home = home / ".m2"
    for directory in (home, temp, maven_user_home / "repository"):
        directory.mkdir(parents=True, exist_ok=True)
    environment.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "TEMP": str(temp),
            "TMP": str(temp),
            "TMPDIR": str(temp),
            "MAVEN_USER_HOME": str(maven_user_home),
            "MAVEN_OPTS": _maven_opts(
                environment.get("MAVEN_OPTS", ""), maven_user_home / "repository"
            ),
        }
    )
    return environment


def _maven_opts(existing: str, repository: Path) -> str:
    repository_option = f'-Dmaven.repo.local="{repository}"'
    return " ".join(value for value in (existing.strip(), repository_option) if value)
