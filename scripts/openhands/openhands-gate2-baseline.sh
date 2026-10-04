#!/usr/bin/env bash
set -euo pipefail

CONTROL_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$CONTROL_REPO"

exec python scripts/openhands/openhands-gate2-baseline.py "$@"
