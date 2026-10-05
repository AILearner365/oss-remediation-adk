#!/usr/bin/env bash
set -euo pipefail

CONTROL_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

exec bash "$CONTROL_REPO/scripts/openhands/openhands-cloudshell-poc.sh" prepare
