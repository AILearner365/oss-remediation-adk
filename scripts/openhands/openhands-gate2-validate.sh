#!/usr/bin/env bash
set -euo pipefail

CONTROL_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$CONTROL_REPO"

# The Gate 2 Stop Hook is launched from an ephemeral OpenHands `uv run`
# environment. Do not let that virtualenv's Python/site-packages leak into the
# independent validator: it can mix OpenHands dependencies with the host ADK
# installation and fail before validation starts.
VALIDATOR_PYTHON="${GATE2_VALIDATOR_PYTHON:-}"
if [ -z "$VALIDATOR_PYTHON" ]; then
  active_venv="${VIRTUAL_ENV:-}"
  while IFS= read -r candidate; do
    [ -n "$candidate" ] || continue
    if [ -n "$active_venv" ] && [[ "$candidate" == "$active_venv/"* ]]; then
      continue
    fi
    VALIDATOR_PYTHON="$candidate"
    break
  done < <(type -aP python3 2>/dev/null || true)
fi

if [ -z "$VALIDATOR_PYTHON" ] || [ ! -x "$VALIDATOR_PYTHON" ]; then
  echo "ERROR: no host Python interpreter available for independent Gate 2 validation" >&2
  exit 70
fi

unset VIRTUAL_ENV
unset PYTHONHOME
unset PYTHONPATH
export PYTHONPATH="$CONTROL_REPO"

exec "$VALIDATOR_PYTHON" scripts/openhands/openhands-gate2-validate.py "$@"
