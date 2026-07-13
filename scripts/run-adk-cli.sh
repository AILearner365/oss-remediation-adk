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

printf 'Starting OSS Remediation ADK CLI...\n'
printf 'Enter the target repository URL and reference branch when prompted.\n\n'

adk run oss_remediation_agent
