#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

HOST="${ADK_HOST:-127.0.0.1}"
PORT="${ADK_PORT:-8000}"

printf 'Starting ADK Web UI at http://%s:%s\n' "$HOST" "$PORT"
printf 'Use this for local development and debugging only.\n\n'

printf 'Allowing Cloud Shell origins for new port %s\n\n' "$PORT"


##adk web --host "$HOST" --port "$PORT"
adk web \
  --host "$HOST" \
  --port "$PORT" \
  --allow_origins "regex:https://${PORT}-cs-[^.]+\\..*\\.cloudshell\\.dev"
