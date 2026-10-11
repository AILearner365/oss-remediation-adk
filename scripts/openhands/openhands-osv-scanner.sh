#!/usr/bin/env bash
# Session-scoped OpenHands OSV launcher; the runner supplies the local Maven registry.
# Both current and legacy recursive source-scan invocations must use that registry.
set -euo pipefail

scanner="${OPENHANDS_OSV_EXECUTABLE:-$HOME/bin/osv-scanner}"
registry="${OPENHANDS_OSV_MAVEN_REGISTRY:-}"

args=("$@")
source_scan=false
if [[ "${1:-}" == "scan" && "${2:-}" == "source" ]]; then
  source_scan=true
elif [[ "${1:-}" == -* ]]; then
  # Older OSV CLI syntax: osv-scanner --format json -r .
  # Normalize only recursive source scans. Do not reinterpret --help,
  # --version, SBOM scans, or other commands.
  recursive=false
  unsupported=false
  for arg in "$@"; do
    case "$arg" in
      -r|--recursive|--recursive=*) recursive=true ;;
      --help|-h|--version|-v|--sbom|--sbom=*|--sbom-file|--sbom-file=*|-L)
        unsupported=true ;;
    esac
  done
  if ! $recursive && ! $unsupported; then
    # Legacy nonrecursive source scans are allowed for focused investigation,
    # but must never look like silent proof of whole-repository clearance.
    echo "OSV_LAUNCHER_SCOPE=NON_RECURSIVE; only explicitly selected files may be scanned. This is not full-project clearance." >&2
  fi
  if $recursive && ! $unsupported; then
    source_scan=true
    args=(scan source "$@")
    echo "OSV_LAUNCHER: normalized legacy recursive scan to 'scan source' with Maven registry" >&2
  fi
fi

if $source_scan; then
  [[ -n "$registry" ]] || {
    echo "INCOMPLETE_SCAN: local Maven registry is not configured" >&2
    exit 2
  }
  clean=()
  skip_next=false
  for arg in "${args[@]}"; do
    if $skip_next; then
      skip_next=false
      continue
    fi
    case "$arg" in
      --data-source|--maven-registry) skip_next=true ;;
      --data-source=*|--maven-registry=*) ;;
      *) clean+=("$arg") ;;
    esac
  done
  exec "$scanner" "${clean[@]}" --data-source=native "--maven-registry=$registry"
fi

exec "$scanner" "$@"
