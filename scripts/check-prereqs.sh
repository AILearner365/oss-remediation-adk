#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

missing=0
warnings=0

ok() {
  printf 'OK: %s\n' "$1"
}

warn() {
  printf 'WARNING: %s\n' "$1" >&2
  warnings=1
}

fail() {
  printf 'MISSING: %s\n' "$1" >&2
  missing=1
}

check_command() {
  local command_name="$1"
  local install_hint="$2"
  if command -v "$command_name" >/dev/null 2>&1; then
    ok "$command_name -> $(command -v "$command_name")"
  else
    fail "$command_name. $install_hint"
  fi
}

printf 'Checking OSS Remediation ADK prerequisites...\n\n'

check_command python3 'Python 3.11 or 3.12 is required.'
check_command git 'Git is required.'
check_command java 'Install the JDK required by the target Maven project.'
check_command javac 'Install a full JDK, not only a JRE.'
check_command mvn 'Install Maven and make mvn available on PATH.'
check_command osv-scanner 'Install OSV Scanner v2 and make it available on PATH.'
check_command gh 'Install GitHub CLI.'
check_command gcloud 'Google Cloud CLI is required for Vertex AI authentication.'

printf '\nChecking Python environment...\n'
if command -v python3 >/dev/null 2>&1; then
  if python3 - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
  then
    ok "Python version is 3.11 or newer ($(python3 --version 2>&1))."
  else
    fail "Python 3.11 or newer is required. Detected: $(python3 --version 2>&1)"
  fi
fi

if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  ok '.venv exists and was activated.'
else
  fail '.venv is missing. Run: bash scripts/setup-local.sh'
fi

if command -v adk >/dev/null 2>&1; then
  ok "ADK CLI -> $(command -v adk)"
else
  fail 'ADK CLI is not installed in the active environment. Run: bash scripts/setup-local.sh'
fi

printf '\nChecking Google Cloud authentication...\n'
if command -v gcloud >/dev/null 2>&1; then
  project="$(gcloud config get-value project 2>/dev/null || true)"
  if [ -n "$project" ] && [ "$project" != "(unset)" ]; then
    ok "Active Google Cloud project: $project"
  else
    warn 'No active Google Cloud project. Run: gcloud config set project YOUR_PROJECT_ID'
  fi

  if gcloud auth application-default print-access-token >/dev/null 2>&1; then
    ok 'Application Default Credentials are available.'
  else
    warn 'Application Default Credentials are missing. Run: gcloud auth application-default login'
  fi
fi

printf '\nChecking GitHub authentication...\n'
if command -v gh >/dev/null 2>&1; then
  if gh auth status >/dev/null 2>&1; then
    ok 'GitHub CLI is authenticated.'
  else
    warn 'GitHub CLI is not authenticated. Run: gh auth login'
  fi
fi

printf '\nChecking project configuration...\n'
if [ -f .env ]; then
  ok '.env exists.'

  for key in GOOGLE_GENAI_USE_VERTEXAI GOOGLE_CLOUD_PROJECT GOOGLE_CLOUD_LOCATION; do
    value="$(grep -E "^${key}=" .env | tail -n 1 | cut -d= -f2- || true)"
    if [ -z "$value" ]; then
      warn "$key is missing or empty in .env."
    elif [ "$value" = "YOUR_PROJECT_ID" ]; then
      warn "$key still contains the placeholder YOUR_PROJECT_ID."
    else
      ok "$key is configured."
    fi
  done
else
  fail '.env is missing. Run: bash scripts/setup-local.sh'
fi

if [ -f requirements.txt ]; then
  ok 'requirements.txt exists.'
else
  fail 'requirements.txt is missing.'
fi

printf '\nChecking tool versions...\n'
command -v java >/dev/null 2>&1 && java -version 2>&1 | head -n 1 || true
command -v mvn >/dev/null 2>&1 && mvn -version 2>/dev/null | head -n 1 || true
command -v osv-scanner >/dev/null 2>&1 && osv-scanner --version 2>/dev/null | head -n 1 || true
command -v gh >/dev/null 2>&1 && gh --version 2>/dev/null | head -n 1 || true

if [ "$missing" -ne 0 ]; then
  printf '\nPrerequisite check failed. Resolve the MISSING items and run this script again.\n' >&2
  exit 1
fi

if [ "$warnings" -ne 0 ]; then
  printf '\nRequired commands are installed, but review the WARNING items before running the workflow.\n'
else
  printf '\nAll prerequisite checks passed.\n'
fi
