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

# Preserve every validator attempt before the next Stop Hook invocation can
# overwrite validation.json or last-validator.log. These snapshots are
# analysis evidence only; the live OUTPUT_FILE remains the acceptance source.
if [ -f "$LAST_LOG" ]; then
  cp -f "$LAST_LOG" "$HOOK_STATE_DIR/validator-attempt-$count.log"
fi
if [ -f "$OUTPUT_FILE" ]; then
  cp -f "$OUTPUT_FILE" "$HOOK_STATE_DIR/validation-attempt-$count.json"
fi

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

summary="$(python - "$OUTPUT_FILE" "$LAST_LOG" "$HOOK_STATE_DIR" "$count" <<'PY'
import json, pathlib, sys

out = pathlib.Path(sys.argv[1])
log = pathlib.Path(sys.argv[2])
history_dir = pathlib.Path(sys.argv[3])
current_attempt = int(sys.argv[4])
parts = []


def _value(data, camel, snake):
    value = data.get(camel)
    return data.get(snake) if value is None else value


def _finding_line(item, current_by_identity=None):
    if not isinstance(item, dict):
        return str(item)
    identity = str(item.get("identity") or item.get("vulnerabilityId") or "UNKNOWN")
    current = (current_by_identity or {}).get(identity, item)
    dep = current.get("dependency") or {}
    group = dep.get("groupId")
    artifact = dep.get("artifactId")
    package = dep.get("packageName")
    coordinate = f"{group}:{artifact}" if group and artifact else str(package or "unknown-package")
    version = str(dep.get("currentVersion") or "unknown-version")
    severity = str(current.get("severity") or item.get("severity") or "UNKNOWN")
    return f"identity={identity}; severity={severity}; package={coordinate}@{version}"


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

        scan = data.get("scan") or {}
        scan_findings = scan.get("findings") or []
        current_by_identity = {
            str(item.get("identity")): item
            for item in scan_findings
            if isinstance(item, dict) and item.get("identity")
        }

        remaining = _value(data, "remainingTargetFindings", "remaining_target_findings")
        if isinstance(remaining, list):
            parts.append(f"Remaining original HIGH/CRITICAL findings: {len(remaining)}")
            if remaining:
                parts.append(
                    "Remaining finding identities/current package versions: "
                    + " | ".join(_finding_line(item, current_by_identity) for item in remaining)
                )

        resolved = _value(data, "resolvedTargetFindings", "resolved_target_findings")
        if isinstance(resolved, list):
            parts.append(f"Current validated progress: {len(resolved)} original findings resolved")
            earlier = []
            for previous in range(1, current_attempt):
                snapshot = history_dir / f"validation-attempt-{previous}.json"
                try:
                    old = json.loads(snapshot.read_text(encoding="utf-8"))
                    prior = _value(old, "resolvedTargetFindings", "resolved_target_findings")
                    if isinstance(prior, list):
                        earlier.append((len(prior), previous))
                except (OSError, ValueError):
                    continue
            if earlier:
                best, previous_attempt = max(earlier)
                parts.append(f"Best earlier validated progress: {best} resolved on attempt {previous_attempt}; earlier attempt may have other failed constraints")
                if best > len(resolved):
                    parts.append("Regression in finding coverage relative to earlier attempt; compare prior evidence and preserve only defensible changes")

        unknown = _value(data, "unknownTargetFindings", "unknown_target_findings")
        if isinstance(unknown, list):
            parts.append(f"Unknown/unscannable original HIGH/CRITICAL findings: {len(unknown)}")
            if unknown:
                parts.append(
                    "Unknown finding identities/baseline package versions: "
                    + " | ".join(_finding_line(item) for item in unknown)
                )

        new_findings = _value(data, "newProhibitedFindings", "new_prohibited_findings")
        if not isinstance(new_findings, list):
            new_findings = None
            for check in checks:
                if check.get("name") == "no_new_prohibited_findings":
                    evidence = check.get("evidence") or {}
                    candidate = evidence.get("newFindings")
                    if isinstance(candidate, list):
                        new_findings = candidate
                    break
        if isinstance(new_findings, list):
            parts.append(f"New prohibited HIGH/CRITICAL findings: {len(new_findings)}")
            if new_findings:
                parts.append(
                    "New prohibited finding identities/package versions: "
                    + " | ".join(_finding_line(item) for item in new_findings)
                )

        for check in checks:
            if check.get("name") == "spring_boot_version_policy" and not check.get("passed", False):
                evidence = check.get("evidence") or {}
                baseline = evidence.get("baseline_version")
                final = evidence.get("final_version")
                if baseline is not None or final is not None:
                    parts.append(f"Spring Boot evidence: baseline={baseline}; current={final}; classification={evidence.get('detected_change_type')}")
            if check.get("name") == "delivery_diff_hygiene" and not check.get("passed", False):
                evidence = check.get("evidence") or {}
                artifacts = evidence.get("diagnosticArtifacts")
                if isinstance(artifacts, list) and artifacts:
                    parts.append("Diagnostic artifacts requiring cleanup: " + ", ".join(map(str, artifacts)))
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
