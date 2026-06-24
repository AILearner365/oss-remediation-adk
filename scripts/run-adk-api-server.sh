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

printf 'Starting ADK API server at http://%s:%s\n' "$HOST" "$PORT"
printf 'Swagger UI should be available at http://%s:%s/docs after startup.\n\n' "$HOST" "$PORT"

adk api_server --host "$HOST" --port "$PORT"
