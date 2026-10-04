#!/usr/bin/env bash
set -euo pipefail

CONTROL_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$CONTROL_REPO"
export PYTHONPATH="$CONTROL_REPO${PYTHONPATH:+:$PYTHONPATH}"

exec python scripts/openhands/openhands-gate2-validate.py "$@"
