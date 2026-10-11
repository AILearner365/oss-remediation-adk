#!/usr/bin/env python3
"""Offline regression check for model-facing Stop Hook feedback (no model or build)."""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "scripts/openhands/openhands-gate2-stop-hook.sh"


def summarize(report: dict) -> str:
    shell = HOOK.read_text(encoding="utf-8")
    pattern = r'summary="\$\(python - "\$OUTPUT_FILE" "\$LAST_LOG" "\$HOOK_STATE_DIR" "\$count" <<\x27PY\x27\n(.*?)\nPY\n\)"'
    match = re.search(pattern, shell, flags=re.DOTALL)
    assert match is not None, "Stop Hook summary Python block not found"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        report_file = root / "validation.json"
        report_file.write_text(json.dumps(report), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-", str(report_file), str(root / "none.log"), tmp, "1"],
            input=match.group(1), capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()


def main() -> None:
    lines = [
        "task-web/pom.xml:+      <exclusions>",
        "task-web/pom.xml:+        <exclusion>",
    ]
    report = {
        "checks": [{
            "name": "suppression_policy", "passed": False,
            "message": "Potential vulnerability suppression change detected",
            "evidence": {"addedSuppressionLines": lines, "changedSuppressionFiles": []},
        }],
        "remainingTargetFindings": [], "resolvedTargetFindings": [],
        "unknownTargetFindings": [],
    }
    result = summarize(report)
    assert "suppression_policy: Potential vulnerability suppression change detected" in result
    for line in lines:
        assert line in result
    assert "Suppression-policy changed lines:" in result

    report["checks"][0]["evidence"] = {"addedSuppressionLines": [], "changedSuppressionFiles": ["security/suppressions.xml"]}
    result = summarize(report)
    assert "Changed suppression files: security/suppressions.xml" in result

    report["checks"][0]["passed"] = True
    result = summarize(report)
    assert "Suppression-policy changed lines:" not in result
    assert "Changed suppression files:" not in result
    print("STOP_HOOK_FEEDBACK_PREFLIGHT=PASS")
    print("model_api_calls=0; validator_policy_unchanged=True")


if __name__ == "__main__":
    main()
