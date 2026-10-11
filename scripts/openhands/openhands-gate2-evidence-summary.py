#!/usr/bin/env python3
"""Summarize persisted Gate-2 independent validation without changing acceptance."""
import json
import re
import sys
from pathlib import Path


def main(evidence_dir: Path) -> int:
    print("==> GATE 2 INDEPENDENT VALIDATION SUMMARY")
    attempts = sorted(
        evidence_dir.glob("validation-attempt-*.json"),
        key=lambda p: int(p.stem.rsplit("-", 1)[-1]),
    )
    if not attempts:
        print("Validator attempts: NOT CAPTURED")
    for path in attempts:
        number = int(path.stem.rsplit("-", 1)[-1])
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"Attempt {number}: REPORT UNREADABLE ({exc})")
            continue
        resolved = len(report.get("resolvedTargetFindings") or [])
        remaining = len(report.get("remainingTargetFindings") or [])
        total = resolved + remaining + len(report.get("unknownTargetFindings") or [])
        scan = report.get("scan") or {}
        stderr = (scan.get("commandResult") or {}).get("stderr") or ""
        pom_paths = set(re.findall(r"Scanned\s+([^\n]+?/pom\.xml)\s+file\b", stderr))
        print(
            f"Attempt {number}: {'PASS' if report.get('passed') else 'FAIL'} "
            f"- resolved {resolved}/{total}; remaining {remaining}; "
            f"scan={scan.get('outcome', 'UNKNOWN')}; "
            f"scanned_poms={len(pom_paths) if pom_paths else 'UNKNOWN'}"
        )
        failures = [c.get("name", "?") for c in report.get("checks") or [] if not c.get("passed")]
        if failures:
            print("  Failed checks: " + ", ".join(failures))
    final_path = evidence_dir / "validation.json"
    if final_path.is_file():
        try:
            final = json.loads(final_path.read_text(encoding="utf-8"))
            print(f"Final independent validation: {'PASS' if final.get('passed') else 'FAIL'}")
            changed = final.get("changedFiles") or []
            diff_path = evidence_dir / "final.diff"
            state_path = evidence_dir / "git-state.txt"
            if changed and (not diff_path.is_file() or not diff_path.stat().st_size):
                print("WARNING: Validator reported changes, but baseline-relative final.diff is missing/empty")
            if state_path.is_file() and "diff_error=" in state_path.read_text(encoding="utf-8"):
                print("WARNING: Final baseline-relative diff could not be captured")
        except (OSError, ValueError) as exc:
            print(f"Final independent validation: UNREADABLE ({exc})")
    else:
        print("Final independent validation: NOT CAPTURED")
    print("==> End Gate 2 validation summary")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: openhands-gate2-evidence-summary.py EVIDENCE_DIR")
    raise SystemExit(main(Path(sys.argv[1])))
