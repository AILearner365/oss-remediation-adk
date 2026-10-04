#!/usr/bin/env bash
set -euo pipefail

TARGET_REPO="${TARGET_REPO:-$HOME/maven-multimodule-app}"
BASE_BRANCH="${BASE_BRANCH:-main-runrunning}"
TASK_BRANCH="${TASK_BRANCH:-openhands-poc-task-01}"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

info() {
  echo "==> $*"
}

[ -d "$TARGET_REPO/.git" ] || die "Target repository not found at $TARGET_REPO. Set TARGET_REPO to the existing maven-multimodule-app checkout."

cd "$TARGET_REPO"

origin_url="$(git remote get-url origin 2>/dev/null || true)"
case "$origin_url" in
  *AILearner365/maven-multimodule-app*) ;;
  *) die "Unexpected origin: ${origin_url:-missing}. Refusing to prepare the wrong repository." ;;
esac

[ -z "$(git status --porcelain)" ] || die "Working tree is not clean. Preserve or discard that work intentionally before Gate 2."

info "Target repository: $TARGET_REPO"
info "Origin: $origin_url"

git fetch origin "$BASE_BRANCH" "$TASK_BRANCH"

base_sha="$(git rev-parse "origin/$BASE_BRANCH")"
task_sha="$(git rev-parse "origin/$TASK_BRANCH")"

git merge-base --is-ancestor "$base_sha" "$task_sha"   || die "$TASK_BRANCH is not based on current origin/$BASE_BRANCH"

if [ "$task_sha" != "$base_sha" ]; then
  info "$TASK_BRANCH already contains commits beyond the current baseline."
  info "This script will not reset or overwrite the branch."
  die "Use a fresh disposable task branch for an uncontaminated Gate 2 run."
fi

if git show-ref --verify --quiet "refs/heads/$TASK_BRANCH"; then
  git switch "$TASK_BRANCH"
  local_sha="$(git rev-parse HEAD)"
  [ "$local_sha" = "$task_sha" ]     || die "Local $TASK_BRANCH differs from origin/$TASK_BRANCH. Refusing to reset it automatically."
else
  git switch --track -c "$TASK_BRANCH" "origin/$TASK_BRANCH"
fi

[ -z "$(git status --porcelain)" ] || die "Working tree became dirty during preparation"

info "Gate 2 target branch ready"
info "Baseline branch: $BASE_BRANCH"
info "Baseline commit: $base_sha"
info "Task branch: $TASK_BRANCH"
info "Task commit: $(git rev-parse HEAD)"
info "Workspace: $TARGET_REPO"

cat <<EOF

NEXT:
1. Verify the HIGH/CRITICAL vulnerability baseline with the approved scanner.
2. Start OpenHands against:
   $TARGET_REPO
3. Paste the task from:
   docs/experiments/openhands/GATE2-TASK.md

Do not feed the old ADK orchestration or known remediation answer into OpenHands.
EOF
