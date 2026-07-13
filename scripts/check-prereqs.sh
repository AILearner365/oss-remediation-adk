#!/usr/bin/env bash
set -euo pipefail

missing=0
warnings=0

check_required() {
  local command_name="$1"
  local install_hint="$2"
  if command -v "$command_name" >/dev/null 2>&1; then
    printf 'OK: %-14s %s\n' "$command_name" "$(command -v "$command_name")"
  else
    printf 'MISSING: %s\n  Install: %s\n' "$command_name" "$install_hint" >&2
    missing=1
  fi
}

printf 'Checking OSS Remediation ADK prerequisites...\n\n'

check_required python3 'https://www.python.org/downloads/ (Python 3.11 or 3.12 recommended)'
check_required git 'https://git-scm.com/downloads'
check_required java 'https://adoptium.net/temurin/releases/ (install the JDK required by the target project)'
check_required javac 'Install a full JDK, not only a JRE: https://adoptium.net/temurin/releases/'
check_required mvn 'https://maven.apache.org/install.html (not required when the target repository has ./mvnw)'
check_required osv-scanner 'https://google.github.io/osv-scanner/installation/'
check_required gh 'https://cli.github.com/'
check_required gcloud 'https://cloud.google.com/sdk/docs/install'

printf '\nChecking Python version...\n'
if command -v python3 >/dev/null 2>&1; then
  python3 - <<'PY'
import sys
required = (3, 11)
print(f"Detected Python {sys.version.split()[0]}")
if sys.version_info < required:
    raise SystemExit("Python 3.11 or newer is required.")
PY
fi

printf '\nChecking GitHub CLI authentication...\n'
if command -v gh >/dev/null 2>&1; then
  if gh auth status >/dev/null 2>&1; then
    printf 'OK: GitHub CLI is authenticated.\n'
  else
    printf 'WARNING: GitHub CLI is not authenticated. Run: gh auth login\n' >&2
    warnings=1
  fi
fi

printf '\nChecking Google Application Default Credentials...\n'
if command -v gcloud >/dev/null 2>&1; then
  if gcloud auth application-default print-access-token >/dev/null 2>&1; then
    printf 'OK: Application Default Credentials are available.\n'
  else
    printf 'WARNING: Application Default Credentials are missing. Run:\n' >&2
    printf '  gcloud auth application-default login\n' >&2
    warnings=1
  fi
fi

printf '\nChecking repository configuration...\n'
if [ -f .env ]; then
  printf 'OK: .env exists.\n'
  for key in GOOGLE_GENAI_USE_ENTERPRISE GOOGLE_CLOUD_PROJECT GOOGLE_CLOUD_LOCATION; do
    if grep -Eq "^${key}=" .env; then
      printf 'OK: %s is configured.\n' "$key"
    else
      printf 'WARNING: %s is missing from .env.\n' "$key" >&2
      warnings=1
    fi
  done
else
  printf 'MISSING: .env\n  Run: bash scripts/setup-local.sh\n' >&2
  missing=1
fi

if [ -f requirements.txt ]; then
  printf 'OK: requirements.txt exists.\n'
else
  printf 'MISSING: requirements.txt\n' >&2
  missing=1
fi

if [ "$missing" -ne 0 ]; then
  printf '\nPrerequisite check failed. Install the missing requirements and rerun this script.\n' >&2
  exit 1
fi

if [ "$warnings" -ne 0 ]; then
  printf '\nAll required commands are installed, but the warnings above must be reviewed.\n'
else
  printf '\nAll prerequisite checks passed.\n'
fi
