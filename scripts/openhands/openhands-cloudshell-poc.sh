#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./openhands-cloudshell-env.sh
source "$SCRIPT_DIR/openhands-cloudshell-env.sh"

CANVAS_VERSION="${CANVAS_VERSION:-1.24.0}"
AGENT_SERVER_VERSION="${OH_AGENT_SERVER_VERSION:-1.50.0}"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

info() {
  echo "==> $*"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

require_cmd node
require_cmd npm

NPM_ROOT="$(npm root -g)"
NPM_PREFIX="$(npm prefix -g)"
CANVAS_ROOT="$NPM_ROOT/@openhands/agent-canvas"
DEV_SAFE="$CANVAS_ROOT/scripts/dev-safe.mjs"
BUILD_DIR="$CANVAS_ROOT/build/assets"
TMUX_DIR="$HOME/.openhands/agent-canvas/tmux"

resolve_canvas_version() {
  [ -f "$CANVAS_ROOT/package.json" ] || return 1
  node -e 'const p=require(process.argv[1]); process.stdout.write(p.version || "")' "$CANVAS_ROOT/package.json"
}

resolve_canvas_bin() {
  if command -v agent-canvas >/dev/null 2>&1; then
    command -v agent-canvas
    return
  fi

  local candidate="$NPM_PREFIX/bin/agent-canvas"
  [ -x "$candidate" ] || die "Agent Canvas executable not found at $candidate"
  printf '%s\n' "$candidate"
}

ensure_canvas_installed() {
  local installed=""
  installed="$(resolve_canvas_version 2>/dev/null || true)"

  if [ "$installed" = "$CANVAS_VERSION" ]; then
    info "Agent Canvas $installed already installed"
    return
  fi

  if [ -n "$installed" ]; then
    die "Agent Canvas $installed is installed, expected $CANVAS_VERSION. Stop and re-evaluate patches before changing versions."
  fi

  info "Agent Canvas is not present in this Cloud Shell session"
  info "Installing @openhands/agent-canvas@$CANVAS_VERSION into the ephemeral global Node location"

  export npm_config_cache="${npm_config_cache:-/tmp/openhands-npm-cache}"
  mkdir -p "$npm_config_cache"

  npm install -g "@openhands/agent-canvas@$CANVAS_VERSION"

  installed="$(resolve_canvas_version 2>/dev/null || true)"
  [ "$installed" = "$CANVAS_VERSION" ] || die "Agent Canvas installation completed but version could not be verified"

  rm -rf "$npm_config_cache" 2>/dev/null || true
  info "Agent Canvas $installed installed"
}


check_versions() {
  require_cmd uv
  require_cmd gcloud
  require_cmd tmux
  require_cmd python

  ensure_canvas_installed

  local installed_canvas
  installed_canvas="$(resolve_canvas_version)"
  [ "$installed_canvas" = "$CANVAS_VERSION" ] || die "Expected Agent Canvas $CANVAS_VERSION, found '${installed_canvas:-unknown}'."

  [ -f "$DEV_SAFE" ] || die "Missing expected launcher file: $DEV_SAFE"

  info "Node: $(node --version)"
  info "npm: $(npm --version)"
  info "uv: $(uv --version)"
  info "tmux: $(tmux -V)"
  info "Agent Canvas: $installed_canvas"
  info "Agent Canvas path: $CANVAS_ROOT"
}

check_versions_prepared() {
  require_cmd uv
  require_cmd gcloud
  require_cmd tmux
  require_cmd python

  local installed_canvas
  installed_canvas="$(resolve_canvas_version 2>/dev/null || true)"
  [ "$installed_canvas" = "$CANVAS_VERSION" ] || die "Expected prepared Agent Canvas $CANVAS_VERSION, found '${installed_canvas:-missing}'. Run startup first."

  [ -f "$DEV_SAFE" ] || die "Missing expected launcher file: $DEV_SAFE"

  info "Node: $(node --version)"
  info "npm: $(npm --version)"
  info "uv: $(uv --version)"
  info "tmux: $(tmux -V)"
  info "Agent Canvas: $installed_canvas"
  info "Agent Canvas path: $CANVAS_ROOT"
}

check_vertex_env() {
  openhands_resolve_vertex_env

  [ -n "${VERTEXAI_PROJECT:-}" ] || die "Vertex project could not be resolved."
  [ -n "${VERTEXAI_LOCATION:-}" ] || die "VERTEXAI_LOCATION is not set"

  gcloud auth application-default print-access-token >/dev/null 2>&1     || die "Application Default Credentials are not available"

  info "ADC OK"
  info "Vertex project: $VERTEXAI_PROJECT"
  info "Vertex location: $VERTEXAI_LOCATION"
}

prepare_runtime() {
  export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/openhands-uv-cache}"
  mkdir -p "$UV_CACHE_DIR"

  mkdir -p "$TMUX_DIR"
  chmod 700 "$TMUX_DIR"

  info "UV cache: $UV_CACHE_DIR"
  info "tmux directory: $TMUX_DIR"
}

patch_vertex_extra() {
  grep -Fq 'openhands-sdk[vertex]==${version}' "$DEV_SAFE" && {
    info "Vertex SDK launcher patch already present"
    return
  }

  grep -Fq 'openhands-sdk==${version}' "$DEV_SAFE"     || die "Expected versioned SDK launcher expression not found. Refusing to patch."

  [ -f "$DEV_SAFE.bak" ] || cp "$DEV_SAFE" "$DEV_SAFE.bak"

  python - "$DEV_SAFE" <<'PY'
from pathlib import Path
import sys

p = Path(sys.argv[1])
s = p.read_text()
old = "`openhands-sdk==${version}`"
new = "`openhands-sdk[vertex]==${version}`"

if old not in s:
    raise SystemExit("Expected launcher expression not found")

p.write_text(s.replace(old, new, 1))
PY

  grep -Fq 'openhands-sdk[vertex]==${version}' "$DEV_SAFE"     || die "Vertex SDK launcher patch verification failed"

  info "Applied Vertex SDK launcher patch"
}

find_readiness_file() {
  local matches=()
  while IFS= read -r f; do
    matches+=("$f")
  done < <(find "$BUILD_DIR" -maxdepth 1 -type f -name 'use-llm-configured-*.js' | sort)

  [ "${#matches[@]}" -eq 1 ]     || die "Expected exactly one use-llm-configured bundle; found ${#matches[@]}"

  printf '%s\n' "${matches[0]}"
}

patch_vertex_readiness() {
  local file
  file="$(find_readiness_file)"

  grep -Fq 'startsWith("vertex_ai/")' "$file" && {
    info "Vertex ADC readiness patch already present"
    return
  }

  grep -Fq 'M=T&&D(O?.config)' "$file"     || die "Expected Canvas readiness expression not found. Refusing to patch."

  [ -f "$file.bak" ] || cp "$file" "$file.bak"

  python - "$file" <<'PY'
from pathlib import Path
import sys

p = Path(sys.argv[1])
s = p.read_text()
old = "M=T&&D(O?.config)"
new = 'M=T&&(D(O?.config)||O?.config?.model?.startsWith("vertex_ai/"))'

if old not in s:
    raise SystemExit("Expected readiness expression not found")

p.write_text(s.replace(old, new, 1))
PY

  grep -Fq 'startsWith("vertex_ai/")' "$file"     || die "Vertex readiness patch verification failed"

  info "Applied Vertex ADC readiness patch"
}

show_disk() {
  df -h /home || true
  du -sh "$HOME/.npm" "$HOME/.cache" "$HOME/.openhands" 2>/dev/null || true
}

verify_tmux() {
  [ -d "$TMUX_DIR" ] || die "OpenHands tmux directory is missing: $TMUX_DIR. Run startup first."
  local session="openhands-verify-$"

  TMUX_TMPDIR="$TMUX_DIR" tmux new-session -d -s "$session" 'sleep 2'     || die "tmux verification failed using $TMUX_DIR"

  TMUX_TMPDIR="$TMUX_DIR" tmux has-session -t "$session" 2>/dev/null     || die "tmux verification session was not created"

  TMUX_TMPDIR="$TMUX_DIR" tmux kill-session -t "$session" 2>/dev/null || true
  info "tmux runtime OK"
}

verify_vertex() {
  check_vertex_env
  [ -d "$UV_CACHE_DIR" ] || die "OpenHands uv cache directory is missing: $UV_CACHE_DIR. Run startup first."

  local result
  result="$(
    uv run --with "openhands-sdk[vertex]==$AGENT_SERVER_VERSION" python - <<'PY'
from openhands.sdk import LLM, Message, TextContent

llm = LLM(
    model="vertex_ai/gemini-2.5-flash",
    api_key=None,
    usage_id="openhands-bootstrap-verify",
)

resp = llm.completion(
    messages=[
        Message(
            role="user",
            content=[TextContent(text="Reply with exactly: VERTEX_OPENHANDS_VERIFY_OK")]
        )
    ]
)

texts = [c.text for c in resp.message.content if isinstance(c, TextContent)]
print(texts[0] if texts else resp.message)
PY
  )" || die "Vertex/OpenHands SDK verification failed"

  printf '%s
' "$result"
  printf '%s
' "$result" | grep -Fq 'VERTEX_OPENHANDS_VERIFY_OK'     || die "Vertex/OpenHands SDK verification returned an unexpected response"

  info "Vertex Gemini smoke test OK"
}

verify_all() {
  check_versions_prepared
  check_effective_patch >/dev/null
  grep -Fq 'openhands-sdk[vertex]==${version}' "$DEV_SAFE" \
    || die "Vertex SDK launcher patch is missing. Run startup first."
  local readiness_file
  readiness_file="$(find_readiness_file)"
  grep -Fq 'startsWith("vertex_ai/")' "$readiness_file" \
    || die "Vertex ADC readiness patch is missing. Run startup first."
  verify_tmux
  verify_vertex
  show_disk
  info "OpenHands Cloud Shell POC verification PASSED"
}

check_effective_patch() {
  grep -n 'openhands-sdk' "$DEV_SAFE" | head -10
  local file
  file="$(find_readiness_file)"
  grep -o 'M=T&&[^,]*' "$file" 2>/dev/null | head -1 || true
}

start_canvas() {
  export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/openhands-uv-cache}"
  export OH_AGENT_SERVER_VERSION="$AGENT_SERVER_VERSION"

  local canvas_bin
  canvas_bin="$(resolve_canvas_bin)"

  info "Starting Agent Canvas"
  info "OH_AGENT_SERVER_VERSION=$OH_AGENT_SERVER_VERSION"
  exec "$canvas_bin"
}

usage() {
  cat <<'EOF'
Usage:
  openhands-cloudshell-poc.sh check
  openhands-cloudshell-poc.sh prepare
  openhands-cloudshell-poc.sh start
  openhands-cloudshell-poc.sh verify
  openhands-cloudshell-poc.sh disk

The script:
- prepare installs/repairs the pinned Cloud Shell runtime and guarded Vertex patches;
- verify is non-repairing and proves the prepared runtime, ADC, tmux, and a real Vertex/OpenHands model call;
- Vertex project resolution order is VERTEXAI_PROJECT, GOOGLE_CLOUD_PROJECT, active gcloud project, then the POC default;
- prepare synchronizes the active gcloud project to the resolved Vertex project when needed;
- /tmp is used for uv cache to protect the small persistent /home volume.

Optional overrides:
  VERTEXAI_PROJECT
  VERTEXAI_LOCATION
  CANVAS_VERSION
  OH_AGENT_SERVER_VERSION
  UV_CACHE_DIR
EOF
}

case "${1:-}" in
  check)
    check_versions
    check_effective_patch
    show_disk
    ;;
  prepare)
    check_versions
    openhands_resolve_vertex_env
    openhands_sync_gcloud_project
    check_vertex_env
    prepare_runtime
    patch_vertex_extra
    patch_vertex_readiness
    check_effective_patch
    show_disk
    ;;
  start)
    check_versions
    check_vertex_env
    prepare_runtime
    patch_vertex_extra
    patch_vertex_readiness
    start_canvas
    ;;
  verify)
    verify_all
    ;;
  disk)
    show_disk
    ;;
  *)
    usage
    exit 2
    ;;
esac
