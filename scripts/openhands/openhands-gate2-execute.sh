#!/usr/bin/env bash
set -euo pipefail

CONTROL_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=./openhands-cloudshell-env.sh
source "$CONTROL_REPO/scripts/openhands/openhands-cloudshell-env.sh"
openhands_resolve_vertex_env

SOURCE_REPO="${SOURCE_REPO:-$HOME/maven-multimodule-app}"
BASE_BRANCH="${BASE_BRANCH:-main-runrunning}"
TASK_ID_RAW="${1:-}"

if [[ ! "$TASK_ID_RAW" =~ ^[0-9]+$ ]]; then
  echo "ERROR: task id is required and must be numeric, for example: 05" >&2
  exit 1
fi
printf -v TASK_ID "%02d" "$((10#$TASK_ID_RAW))"

TASK_BRANCH="${TASK_BRANCH:-openhands-poc-task-${TASK_ID}-stop-hook}"
TARGET_REPO="${TARGET_REPO:-$HOME/maven-multimodule-app-stop-hook-${TASK_ID}}"
STATE_DIR="${STATE_DIR:-$HOME/.openhands/gate2/task-${TASK_ID}-stop-hook}"
MODEL="${MODEL:-vertex_ai/gemini-2.5-flash}"
MAX_DENIALS="${MAX_DENIALS:-3}"
MAX_ITERATIONS="${MAX_ITERATIONS:-250}"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

info() {
  echo "==> $*"
}

info "Gate 2 execution"
info "Task: $TASK_ID"
info "Vertex project: $VERTEXAI_PROJECT"
info "Vertex location: $VERTEXAI_LOCATION"
info "Model: $MODEL"
info "Source repo: $SOURCE_REPO"
info "Target worktree: $TARGET_REPO"
info "State directory: $STATE_DIR"

info "Verifying refreshable Python ADC before creating task state"
openhands_verify_vertex_adc "$CONTROL_REPO" "1.50.0" \
  || die "Python ADC refresh failed. Reauthorize or restart Cloud Shell before running OpenHands."

git -C "$SOURCE_REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || die "Source repository not found at $SOURCE_REPO"

origin_url="$(git -C "$SOURCE_REPO" remote get-url origin 2>/dev/null || true)"
case "$origin_url" in
  *AILearner365/maven-multimodule-app*) ;;
  *) die "Unexpected source repository origin: ${origin_url:-missing}" ;;
esac

[ ! -e "$TARGET_REPO" ] || die "Target worktree already exists: $TARGET_REPO"
[ ! -e "$STATE_DIR" ] || die "State directory already exists: $STATE_DIR"

info "Fetching baseline"
git -C "$SOURCE_REPO" fetch origin \
  "+refs/heads/$BASE_BRANCH:refs/remotes/origin/$BASE_BRANCH"

base_sha="$(git -C "$SOURCE_REPO" rev-parse "origin/$BASE_BRANCH")"
info "Baseline: $BASE_BRANCH @ $base_sha"

if git -C "$SOURCE_REPO" show-ref --verify --quiet "refs/remotes/origin/$TASK_BRANCH"; then
  task_sha="$(git -C "$SOURCE_REPO" rev-parse "origin/$TASK_BRANCH")"
  [ "$task_sha" = "$base_sha" ] \
    || die "Remote $TASK_BRANCH already exists beyond the baseline. Use a new task id."
  info "Reusing clean remote task branch: $TASK_BRANCH"
else
  info "Creating remote task branch: $TASK_BRANCH"
  git -C "$SOURCE_REPO" push origin "$base_sha:refs/heads/$TASK_BRANCH"
  git -C "$SOURCE_REPO" fetch origin \
    "+refs/heads/$TASK_BRANCH:refs/remotes/origin/$TASK_BRANCH"
fi

if git -C "$SOURCE_REPO" show-ref --verify --quiet "refs/heads/$TASK_BRANCH"; then
  local_sha="$(git -C "$SOURCE_REPO" rev-parse "$TASK_BRANCH")"
  [ "$local_sha" = "$base_sha" ] \
    || die "Local $TASK_BRANCH exists beyond the baseline. Use a new task id."
  info "Adding worktree from existing clean local branch"
  git -C "$SOURCE_REPO" worktree add "$TARGET_REPO" "$TASK_BRANCH"
else
  info "Creating fresh worktree"
  git -C "$SOURCE_REPO" worktree add -b "$TASK_BRANCH" "$TARGET_REPO" "origin/$TASK_BRANCH"
fi

mkdir -p "$STATE_DIR"

info "Running deterministic baseline"
cd "$CONTROL_REPO"
bash scripts/openhands/openhands-gate2-baseline.sh \
  --target-repo "$TARGET_REPO" \
  --base-branch "$BASE_BRANCH" \
  --task-branch "$TASK_BRANCH" \
  --state-file "$STATE_DIR/baseline.json"

info "Starting OpenHands Gate 2 run"
UV_CACHE_DIR="$UV_CACHE_DIR" \
uv run \
  --with "openhands-sdk[vertex]==1.50.0" \
  --with "openhands-tools==1.50.0" \
  python scripts/openhands/openhands-gate2-stop-hook-run.py \
  --target-repo "$TARGET_REPO" \
  --state-dir "$STATE_DIR" \
  --model "$MODEL" \
  --max-denials "$MAX_DENIALS" \
  --max-iterations "$MAX_ITERATIONS"
