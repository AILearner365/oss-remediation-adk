#!/usr/bin/env bash
# Session-scoped OpenHands OSV launcher; the runner supplies the local Maven registry.
set -euo pipefail
scanner="${OPENHANDS_OSV_EXECUTABLE:-$HOME/bin/osv-scanner}"
if [[ "${1:-}" == "scan" && "${2:-}" == "source" ]]; then
  [[ -n "${OPENHANDS_OSV_MAVEN_REGISTRY:-}" ]] || {
    echo "INCOMPLETE_SCAN: local Maven registry is not configured" >&2
    exit 2
  }
  exec "$scanner" "$@" --data-source=native "--maven-registry=$OPENHANDS_OSV_MAVEN_REGISTRY"
fi
exec "$scanner" "$@"
