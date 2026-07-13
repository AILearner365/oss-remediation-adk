#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  printf 'Python 3 is required. Install Python 3.11 or 3.12 from https://www.python.org/downloads/\n' >&2
  exit 1
fi

printf 'Creating local Python virtual environment...\n'
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
