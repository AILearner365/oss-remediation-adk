#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f .venv/bin/activate ]; then
  printf 'ERROR: .venv is missing. Run: bash scripts/setup-local.sh\n' >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if [ ! -f .env ]; then
  printf 'ERROR: .env is missing. Run setup-local.sh and configure .env.\n' >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

if ! command -v adk >/dev/null 2>&1; then
  printf 'ERROR: adk command not found. Run: bash scripts/setup-local.sh\n' >&2
  exit 1
fi

HOST="${ADK_HOST:-0.0.0.0}"
PORT="${ADK_PORT:-8000}"

printf 'Starting ADK Web for oss_remediation_agent...\n'
printf 'Host: %s\n' "$HOST"
printf 'Port: %s\n' "$PORT"
printf 'In Google Cloud Shell, open Web Preview for port %s.\n\n' "$PORT"

adk web . \
  --host "$HOST" \
  --port "$PORT" \
  --allow_origins "regex:https://${PORT}-cs-[^.]+\\..*\\.cloudshell\\.dev" \
  --no-reload
