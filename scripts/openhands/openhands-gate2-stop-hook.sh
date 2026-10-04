#!/usr/bin/env bash
set -euo pipefail

CONTROL_REPO="${CONTROL_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
STATE_FILE="${GATE2_STATE_FILE:-$HOME/.openhands/gate2/task-02-stop-hook/baseline.json}"
OUTPUT_FILE="${GATE2_VALIDATION_OUTPUT:-$HOME/.openhands/gate2/task-02-stop-hook/validation.json}"
HOOK_STATE_DIR="${GATE2_HOOK_STATE_DIR:-$HOME/.openhands/gate2/task-02-stop-hook/hook}"
TARGET_REPO="${GATE2_TARGET_REPO:-$HOME/maven-multimodule-app-stop-hook}"
MAX_DENIALS="${GATE2_MAX_DENIALS:-3}"

mkdir -p "$HOOK_STATE_DIR"
COUNT_FILE="$HOOK_STATE_DIR/attempt-count"
LAST_LOG="$HOOK_STATE_DIR/last-validator.log"
INFRA_FILE="$HOOK_STATE_DIR/infrastructure-failure"

count=0
if [ -f "$COUNT_FILE" ]; then
  count="$(cat "$COUNT_FILE")"
fi
count=$((count + 1))
printf '%s\n' "$count" > "$COUNT_FILE"

rm -f "$OUTPUT_FILE" "$INFRA_FILE"

set +e
bash "$CONTROL_REPO/scripts/openhands/openhands-gate2-validate.sh" \
  --target-repo "$TARGET_REPO" \
  --state-file "$STATE_FILE" \
  --output "$OUTPUT_FILE" \
  >"$LAST_LOG" 2>&1
rc=$?
set -e

if [ "$rc" -eq 0 ]; then
  python - "$count" "$OUTPUT_FILE" <<'PY'
import json, sys
attempt = int(sys.argv[1])
print(json.dumps({
    "decision": "allow",
    "reason": f"Gate 2 deterministic validator passed on stop attempt {attempt}."
}))
PY
  exit 0
fi

if [ ! -s "$OUTPUT_FILE" ]; then
  printf '%s\n' "validator_exit_code=$rc" > "$INFRA_FILE"
  python - "$count" "$rc" "$LAST_LOG" <<'PY'
import json, pathlib, sys
attempt = int(sys.argv[1])
rc = int(sys.argv[2])
log = pathlib.Path(sys.argv[3])
lines = [line.strip() for line in log.read_text(errors="replace").splitlines() if line.strip()] if log.is_file() else []
tail = " | ".join(lines[-12:]) if lines else "no validator output"
print(json.dumps({
    "decision": "allow",
    "reason": (
        f"Gate 2 validator infrastructure failure on stop attempt {attempt} "
        f"(exit {rc}); ending the experiment without deterministic acceptance. "
        + tail
    ),
}))
PY
  exit 0
fi

summary="$(python - "$OUTPUT_FILE" "$LAST_LOG" <<'PY'
import json, pathlib, sys
out = pathlib.Path(sys.argv[1])
log = pathlib.Path(sys.argv[2])
parts = []
if out.is_file():
    try:
        data = json.loads(out.read_text())
        checks = data.get("checks") or []
        failed = []
        for check in checks:
            if not check.get("passed", False):
                name = check.get("name", "unnamed_check")
                msg = str(check.get("message", "")).strip()
                failed.append(f"{name}: {msg}" if msg else name)
        if failed:
            parts.append("Failed deterministic checks: " + " | ".join(failed[:8]))
        remaining = data.get("remainingTargetFindings")
        if remaining is None:
            remaining = data.get("remaining_target_findings")
        if isinstance(remaining, list):
            parts.append(f"Remaining original HIGH/CRITICAL findings: {len(remaining)}")
        unknown = data.get("unknownTargetFindings")
        if unknown is None:
            unknown = data.get("unknown_target_findings")
        if isinstance(unknown, list):
            parts.append(f"Unknown/unscannable original HIGH/CRITICAL findings: {len(unknown)}")
        new_findings = data.get("newProhibitedFindings")
        if new_findings is None:
            new_findings = data.get("new_prohibited_findings")
        if isinstance(new_findings, list):
            parts.append(f"New prohibited HIGH/CRITICAL findings: {len(new_findings)}")
    except Exception as exc:
        parts.append(f"Validation report could not be summarized: {exc}")
if not parts and log.is_file():
    lines = [line.strip() for line in log.read_text(errors="replace").splitlines() if line.strip()]
    tail = lines[-12:]
    if tail:
        parts.append("Validator output: " + " | ".join(tail))
if not parts:
    parts.append("Deterministic validator failed without a readable report.")
print(" ".join(parts))
PY
)"

if [ "$count" -le "$MAX_DENIALS" ]; then
  python - "$count" "$summary" <<'PY'
import json, sys
attempt = int(sys.argv[1])
summary = sys.argv[2]
print(json.dumps({
    "decision": "deny",
    "reason": f"Gate 2 deterministic validator failed on stop attempt {attempt}.",
    "additionalContext": (
        "DETERMINISTIC_VALIDATION_FAILED: " + summary +
        " Reassess using this evidence. Do not treat the failure as a prescribed solution; "
        "choose and validate the next engineering action yourself."
    ),
}))
PY
  exit 2
fi

# Bound the experiment. We allow the conversation to terminate after the configured
# number of denied completions, but this is NOT acceptance. The outer runner reads
# validation.json and exits nonzero unless the validator passed.
python - "$count" "$MAX_DENIALS" "$summary" <<'PY'
import json, sys
attempt = int(sys.argv[1])
limit = int(sys.argv[2])
summary = sys.argv[3]
print(json.dumps({
    "decision": "allow",
    "reason": (
        f"Experiment bound reached after {limit} denied completion attempts; "
        f"attempt {attempt} is allowed only to terminate the experiment. "
        "Deterministic acceptance has NOT passed. " + summary
    ),
}))
PY
exit 0
