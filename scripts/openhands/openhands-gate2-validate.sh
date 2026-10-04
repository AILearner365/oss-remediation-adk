#!/usr/bin/env bash
set -euo pipefail

CONTROL_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$CONTROL_REPO"

# The Gate 2 Stop Hook is launched from an ephemeral OpenHands `uv run`
# environment. The validator must execute with the host interpreter that owns
# this repository's ADK/runtime dependencies, not with the temporary OpenHands
# virtualenv and not with an arbitrary system python3 lacking those packages.
VALIDATOR_PYTHON="${GATE2_VALIDATOR_PYTHON:-}"
if [ -z "$VALIDATOR_PYTHON" ]; then
  active_venv="${VIRTUAL_ENV:-}"
  while IFS= read -r candidate; do
    [ -n "$candidate" ] || continue
    if [ -n "$active_venv" ] && [[ "$candidate" == "$active_venv/"* ]]; then
      continue
    fi
    if env -u VIRTUAL_ENV -u PYTHONHOME -u PYTHONPATH \
      "$candidate" -c 'import google.adk; import pydantic' >/dev/null 2>&1; then
      VALIDATOR_PYTHON="$candidate"
      break
    fi
  done < <(
    {
      type -aP python 2>/dev/null || true
      type -aP python3 2>/dev/null || true
    } | awk '!seen[$0]++'
  )
fi

if [ -z "$VALIDATOR_PYTHON" ] || [ ! -x "$VALIDATOR_PYTHON" ]; then
  echo "ERROR: no host Python interpreter with required Gate 2 validator dependencies (google.adk, pydantic) was found" >&2
  exit 70
fi

unset VIRTUAL_ENV
unset PYTHONHOME
unset PYTHONPATH
export PYTHONPATH="$CONTROL_REPO"

exec "$VALIDATOR_PYTHON" scripts/openhands/openhands-gate2-validate.py "$@"
