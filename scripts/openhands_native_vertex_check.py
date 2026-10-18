#!/usr/bin/env python3
"""Read-only reuse of the existing Gate-2 Vertex environment resolver.

No model invocation, no SDK installation, no gcloud project mutation, no
credentials printed and no /run. Project resolution is NOT proof of ADC.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ENV_SCRIPT = ROOT / "scripts" / "openhands" / "openhands-cloudshell-env.sh"
MODEL = "vertex_ai/gemini-2.5-flash"


def resolve_existing_vertex_environment(script: Path = ENV_SCRIPT) -> dict:
    if not script.is_file():
        raise ValueError("Existing Cloud Shell Vertex resolver missing")
    # Source only the existing function; do not call sync_gcloud_project,
    # ADC refresh, SDK verify_vertex or model completion.
    completed = subprocess.run(
        ["bash", "-c", 'source "$1"; openhands_resolve_vertex_env; printf "%s\\n" "$VERTEXAI_PROJECT" "$VERTEXAI_LOCATION"',
         "native-vertex-readonly", str(script)],
        capture_output=True, text=True, timeout=20, check=True,
    )
    lines = completed.stdout.splitlines()
    if len(lines) != 2 or not all(lines):
        raise ValueError("Vertex environment resolver returned incomplete configuration")
    return {
        "model": MODEL, "vertexProject": lines[0], "vertexLocation": lines[1],
        "source": "scripts/openhands/openhands-cloudshell-env.sh",
        "environmentResolved": True,
        "adcRefreshVerified": False,
        "native1551VertexExtraVerified": False,
        "modelRequestPerformed": False,
        "modelExecutionAuthorized": False,
        "nextCheck": (
            "Use existing scripts/openhands/vertex-adc-preflight.py with the "
            "actual installed 1.55.1 Vertex SDK runtime, without calling verify_vertex."
        ),
    }


def main() -> int:
    try:
        print(json.dumps(resolve_existing_vertex_environment(), indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError):
        print(json.dumps({"environmentResolved": False, "modelExecutionAuthorized": False,
                          "modelRequestPerformed": False, "status": "BLOCKED"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
