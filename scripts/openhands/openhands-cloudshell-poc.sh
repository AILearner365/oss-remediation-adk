#!/usr/bin/env bash
set -euo pipefail

CANVAS_VERSION="${CANVAS_VERSION:-1.24.0}"
AGENT_SERVER_VERSION="${OH_AGENT_SERVER_VERSION:-1.50.0}"
NPM_ROOT="$(npm root -g)"
CANVAS_ROOT="$NPM_ROOT/@openhands/agent-canvas"
DEV_SAFE="$CANVAS_ROOT/scripts/dev-safe.mjs"
BUILD_DIR="$CANVAS_ROOT/build/assets"
TMUX_DIR="$HOME/.openhands/agent-canvas/tmux"

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

check_versions() {
  require_cmd node
  require_cmd npm
  require_cmd uv
  require_cmd gcloud
  require_cmd tmux
  require_cmd python

  local installed_canvas
  installed_canvas="$(node -e 'const p=require(process.argv[1]); process.stdout.write(p.version || "")' "$CANVAS_ROOT/package.json" 2>/dev/null || true)"
  [ "$installed_canvas" = "$CANVAS_VERSION" ] || die "Expected Agent Canvas $CANVAS_VERSION, found '${installed_canvas:-unknown}'. Stop and re-evaluate patches."

  [ -f "$DEV_SAFE" ] || die "Missing expected launcher file: $DEV_SAFE"

  info "Node: $(node --version)"
  info "npm: $(npm --version)"
  info "uv: $(uv --version)"
  info "tmux: $(tmux -V)"
  info "Agent Canvas: $installed_canvas"
  info "Agent Canvas path: $CANVAS_ROOT"
}

check_vertex_env() {
  [ -n "${VERTEXAI_PROJECT:-}" ] || die "VERTEXAI_PROJECT is not set"
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

check_effective_patch() {
  grep -n 'openhands-sdk' "$DEV_SAFE" | head -10
  local file
  file="$(find_readiness_file)"
  grep -o 'M=T&&[^,]*' "$file" 2>/dev/null | head -1 || true
}

start_canvas() {
  export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/openhands-uv-cache}"
  export OH_AGENT_SERVER_VERSION="$AGENT_SERVER_VERSION"

  info "Starting Agent Canvas"
  info "OH_AGENT_SERVER_VERSION=$OH_AGENT_SERVER_VERSION"
  local canvas_bin
  canvas_bin="$(command -v agent-canvas || true)"
  [ -n "$canvas_bin" ] || canvas_bin="$(npm prefix -g)/bin/agent-canvas"
  [ -x "$canvas_bin" ] || die "Agent Canvas executable not found: $canvas_bin"
  exec "$canvas_bin"
}

usage() {
  cat <<'EOF'
Usage:
  openhands-cloudshell-poc.sh check
  openhands-cloudshell-poc.sh prepare
  openhands-cloudshell-poc.sh start
  openhands-cloudshell-poc.sh disk

Environment required for prepare/start:
  VERTEXAI_PROJECT
  VERTEXAI_LOCATION

Optional:
  CANVAS_VERSION          default: 1.24.0
  OH_AGENT_SERVER_VERSION default: 1.50.0
  UV_CACHE_DIR            default: /tmp/openhands-uv-cache
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
  disk)
    show_disk
    ;;
  *)
    usage
    exit 2
    ;;
esac
