#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  printf 'ERROR: python3 is required. Use Python 3.11 or 3.12.\n' >&2
  exit 1
fi

python3 - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("ERROR: Python 3.11 or newer is required.")
print(f"Using Python {sys.version.split()[0]}")
PY

if [ ! -d .venv ]; then
  printf 'Creating Python virtual environment at .venv...\n'
  python3 -m venv .venv
else
  printf 'Using existing Python virtual environment at .venv.\n'
fi

# shellcheck disable=SC1091
source .venv/bin/activate

printf 'Upgrading pip...\n'
python -m pip install --upgrade pip

printf 'Installing Python dependencies from requirements.txt...\n'
python -m pip install -r requirements.txt

if [ ! -f .env ]; then
  if [ ! -f .env.example ]; then
    printf 'ERROR: .env.example is missing.\n' >&2
    exit 1
  fi
  cp .env.example .env
  printf 'Created .env from .env.example.\n'
else
  printf 'Keeping the existing .env file unchanged.\n'
fi

printf '\nSetup completed.\n'
printf 'Next steps:\n'
printf '  1. Update GOOGLE_CLOUD_PROJECT in .env.\n'
printf '  2. Install OSV Scanner if `osv-scanner --version` fails.\n'
printf '  3. Authenticate GitHub with `gh auth login`.\n'
printf '  4. Run `bash scripts/check-prereqs.sh`.\n'
printf '  5. Start ADK Web with `bash scripts/run-adk-web.sh`.\n'
