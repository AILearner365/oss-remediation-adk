#!/usr/bin/env bash
# Standalone OpenHands SDK Cloud Shell setup, distilled from the Gate 2 POC.
# No Canvas, Agent Server, tmux, paid inference or repository mutation.
set -euo pipefail

SDK_VERSION="1.55.1"
RUNTIME_ROOT="${OPENHANDS_RUNTIME_ROOT:-/tmp/openhands-sdk-1.55.1}"
VENV="$RUNTIME_ROOT/venv"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/openhands-uv-cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-/tmp/openhands-uv-python}"
export TMPDIR="${TMPDIR:-/tmp}"
PY="$VENV/bin/python"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '==> %s\n' "$*"; }
require() { command -v "$1" >/dev/null 2>&1 || die "Missing $1"; }

resolve_vertex() {
  if [ -z "${VERTEXAI_PROJECT:-}" ]; then
    VERTEXAI_PROJECT="${GOOGLE_CLOUD_PROJECT:-}"
  fi
  if [ -z "$VERTEXAI_PROJECT" ] && command -v gcloud >/dev/null 2>&1; then
    VERTEXAI_PROJECT="$(gcloud config get-value project 2>/dev/null || true)"
    [ "$VERTEXAI_PROJECT" != "(unset)" ] || VERTEXAI_PROJECT=""
  fi
  # Historical POC fallback, only if no active project has been supplied/discovered.
  VERTEXAI_PROJECT="${VERTEXAI_PROJECT:-deutschebank-aipocs}"
  VERTEXAI_LOCATION="${VERTEXAI_LOCATION:-us-central1}"
  export VERTEXAI_PROJECT VERTEXAI_LOCATION
}

check_install() {
  [ -x "$PY" ] || return 1
  "$PY" -c "from importlib.metadata import version; assert version('openhands-sdk') == '$SDK_VERSION'; assert version('openhands-tools') == '$SDK_VERSION'; from openhands.sdk import Conversation; from openhands.tools.terminal import TerminalTool" >/dev/null 2>&1
}

show() {
  info "SDK: $SDK_VERSION"
  info "Python: $PY"
  info "UV cache: $UV_CACHE_DIR"
  info "UV managed Python: $UV_PYTHON_INSTALL_DIR"
  info "Vertex project: $VERTEXAI_PROJECT"
  info "Vertex location: $VERTEXAI_LOCATION"
  df -h /home /tmp | awk 'NR==1 || !seen[$1]++'
}

prepare() {
  require uv
  if check_install; then
    info "Reusing installed SDK at $VENV"
  else
    info "Preparing SDK $SDK_VERSION on temporary filesystem (not /home)"
    for directory in "$RUNTIME_ROOT" "$UV_CACHE_DIR" "$UV_PYTHON_INSTALL_DIR"; do
      case "$directory/" in /tmp/*) ;; *) die "Refusing installation outside /tmp: $directory";; esac
    done
    mkdir -p "$RUNTIME_ROOT" "$UV_CACHE_DIR" "$UV_PYTHON_INSTALL_DIR"
    uv venv --python 3.12 "$VENV"
    uv pip install --python "$PY" "openhands-sdk[vertex]==$SDK_VERSION" "openhands-tools==$SDK_VERSION"
    check_install || die "Installed SDK failed import/version checks"
  fi
}

verify() {
  check_install || die "SDK not installed in $VENV; run prepare"
  info "Checking installed SDK and Vertex ADC (no model calls)"
  "$PY" - <<'PY'
import os
from importlib.metadata import version
import google.auth
from google.auth.transport.requests import Request
for pkg in ("openhands-sdk", "openhands-tools"):
    print(f"{pkg}: {version(pkg)}")
creds, detected_project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
creds.refresh(Request())
assert creds.valid and creds.token, "ADC refresh failed"
assert os.environ["VERTEXAI_PROJECT"] and os.environ["VERTEXAI_LOCATION"]
if detected_project:
    assert detected_project == os.environ["VERTEXAI_PROJECT"], "ADC project mismatch"
print("Vertex ADC: refreshed (credentials not printed)")
print("Vertex project:", os.environ["VERTEXAI_PROJECT"])
print("Vertex location:", os.environ["VERTEXAI_LOCATION"])
PY
}

resolve_vertex
case "${1:-}" in
  prepare) prepare; show ;;
  verify) verify; show ;;
  test)
    check_install || die "SDK missing; run prepare"
    cd "$REPO"
    "$PY" -m unittest tests_native.test_product tests_native.test_sdk_contract tests_native.test_local_execution tests_native.test_parity tests_native.test_sdk_parity -v
    ;;
  python)
    check_install || die "SDK missing; run prepare"
    shift
    exec "$PY" "$@"
    ;;
  status) show; check_install && info "SDK ready" || info "SDK missing; run prepare" ;;
  *)
    cat <<'USAGE'
Usage: bash scripts/openhands/sdk-cloudshell-setup.sh prepare|verify|test|status|python [args...]

prepare  Reuse or install pinned SDK/tools 1.55.1 in /tmp, using /tmp UV caches.
verify   Check installed SDK and refresh Vertex ADC without invoking Gemini.
test     Run local SDK and product unit tests (no Gemini calls).
status   Show configured locations and presence, without installing.
python   Run arguments using the prepared SDK Python.

Cloud Shell /tmp may be wiped on restart; rerun prepare when needed.
Optional: VERTEXAI_PROJECT, VERTEXAI_LOCATION, OPENHANDS_RUNTIME_ROOT,
UV_CACHE_DIR, UV_PYTHON_INSTALL_DIR (installation paths must be under /tmp).
USAGE
    exit 2
    ;;
esac
