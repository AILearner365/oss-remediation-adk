#!/usr/bin/env bash
set -euo pipefail

CONTROL_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SOURCE_REPO="${SOURCE_REPO:-$HOME/maven-multimodule-app}"
LOG_ROOT="${OPENHANDS_RUN_LOG_ROOT:-$HOME/.openhands/gate2/run-logs}"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_LOG_DIR="$LOG_ROOT/run-$RUN_ID"
mkdir -p "$RUN_LOG_DIR"

exec > >(tee -a "$RUN_LOG_DIR/combined.log") 2>&1

die() {
  echo "ERROR: $*" >&2
  echo "Logs: $RUN_LOG_DIR" >&2
  exit 1
}

info() {
  echo "==> $*"
}

next_task_id() {
  local max=4 value ref path
  while IFS= read -r ref; do
    value="${ref##*openhands-poc-task-}"
    value="${value%%-stop-hook*}"
    if [[ "$value" =~ ^[0-9]+$ ]] && ((10#$value > max)); then
      max=$((10#$value))
    fi
  done < <(
    {
      git -C "$SOURCE_REPO" ls-remote --heads origin 'refs/heads/openhands-poc-task-*-stop-hook' 2>/dev/null | awk '{print $2}'
      git -C "$SOURCE_REPO" for-each-ref --format='%(refname)' 'refs/heads/openhands-poc-task-*-stop-hook' 2>/dev/null
    } || true
  )

  for path in "$HOME"/maven-multimodule-app-stop-hook-* "$HOME"/.openhands/gate2/task-*-stop-hook; do
    [ -e "$path" ] || continue
    value="${path##*-}"
    if [[ "$value" =~ ^[0-9]+$ ]] && ((10#$value > max)); then
      max=$((10#$value))
    fi
  done

  printf '%02d\n' "$((max + 1))"
}

TASK_ID_RAW="${1:-}"
if [ -n "$TASK_ID_RAW" ]; then
  [[ "$TASK_ID_RAW" =~ ^[0-9]+$ ]] || die "Task id must be numeric, for example: 05"
  printf -v TASK_ID "%02d" "$((10#$TASK_ID_RAW))"
else
  git -C "$SOURCE_REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
    || die "Source repository not found at $SOURCE_REPO"
  TASK_ID="$(next_task_id)"
fi

printf '%s\n' "$TASK_ID" > "$RUN_LOG_DIR/task-id.txt"

info "OpenHands Gate 2 orchestrated run"
info "Run logs: $RUN_LOG_DIR"
info "Task: $TASK_ID"

info "Stage 1/3: STARTUP / PREPARE"
bash "$CONTROL_REPO/scripts/openhands/openhands-cloudshell-startup.sh" \
  2>&1 | tee "$RUN_LOG_DIR/startup.log"

info "Stage 2/3: VERIFY"
bash "$CONTROL_REPO/scripts/openhands/openhands-cloudshell-verify.sh" \
  2>&1 | tee "$RUN_LOG_DIR/verify.log"

info "Stage 3/3: EXECUTE"
bash "$CONTROL_REPO/scripts/openhands/openhands-gate2-execute.sh" "$TASK_ID" \
  2>&1 | tee "$RUN_LOG_DIR/execute.log"

info "Run completed"
info "Task: $TASK_ID"
info "Logs: $RUN_LOG_DIR"
