#!/usr/bin/env bash
# Session-scoped OpenHands OSV launcher; the runner supplies the local Maven registry.
set -euo pipefail
scanner="${OPENHANDS_OSV_EXECUTABLE:-$HOME/bin/osv-scanner}"
if [[ "${1:-}" == "scan" && "${2:-}" == "source" ]]; then
  [[ -n "${OPENHANDS_OSV_MAVEN_REGISTRY:-}" ]] || {
    echo "INCOMPLETE_SCAN: local Maven registry is not configured" >&2
    exit 2
  }
  args=()
  skip_next=false
  for arg in "$@"; do
    if $skip_next; then
      skip_next=false
      continue
    fi
    case "$arg" in
      --data-source|--maven-registry) skip_next=true ;;
      --data-source=*|--maven-registry=*) ;;
      *) args+=("$arg") ;;
    esac
  done
  exec "$scanner" "${args[@]}" --data-source=native "--maven-registry=$OPENHANDS_OSV_MAVEN_REGISTRY"
fi
exec "$scanner" "$@"
