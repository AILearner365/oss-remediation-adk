#!/usr/bin/env bash
set -euo pipefail

missing=0

check_required() {
  local command_name="$1"
  local install_hint="$2"

  if command -v "$command_name" >/dev/null 2>&1; then
    printf 'OK: %s found at %s\n' "$command_name" "$(command -v "$command_name")"
  else
    printf 'MISSING: %s\n  Install hint: %s\n' "$command_name" "$install_hint" >&2
    missing=1
  fi
}

printf 'Checking required local tools for OSS remediation ADK workflow...\n\n'

check_required python3 'Install Python 3.10+.'
check_required git 'Install Git and ensure it is available on PATH.'
check_required java 'Install a JDK compatible with the target Maven project.'
check_required mvn 'Install Apache Maven and ensure mvn is available on PATH.'
check_required osv-scanner 'Install OSV Scanner: https://google.github.io/osv-scanner/installation/'
check_required gh 'Install GitHub CLI and run: gh auth login'

printf '\nChecking optional ADK CLI...\n'
if command -v adk >/dev/null 2>&1; then
  printf 'OK: adk found at %s\n' "$(command -v adk)"
else
  printf 'INFO: adk CLI not found yet. Run scripts/setup-local.sh or install requirements.txt first.\n'
fi

printf '\nChecking GitHub CLI authentication...\n'
if command -v gh >/dev/null 2>&1; then
  if gh auth status >/dev/null 2>&1; then
    printf 'OK: gh is authenticated.\n'
  else
    printf 'WARNING: gh is installed but not authenticated. Agent 3 PR creation requires: gh auth login\n'
  fi
fi

if [ "$missing" -ne 0 ]; then
  printf '\nOne or more required tools are missing. Install them and rerun this script.\n' >&2
  exit 1
fi

printf '\nAll required tools are available.\n'
