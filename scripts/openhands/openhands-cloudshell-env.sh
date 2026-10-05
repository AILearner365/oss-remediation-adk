#!/usr/bin/env bash
# Shared OpenHands Cloud Shell environment resolution.
# This file is intended to be sourced by the startup, verify, and run scripts.

DEFAULT_VERTEX_PROJECT="${DEFAULT_VERTEX_PROJECT:-deutschebank-aipocs}"
DEFAULT_VERTEX_LOCATION="${DEFAULT_VERTEX_LOCATION:-us-central1}"
DEFAULT_UV_CACHE_DIR="${DEFAULT_UV_CACHE_DIR:-/tmp/openhands-uv-cache}"

openhands_resolve_vertex_env() {
  if [ -z "${VERTEXAI_PROJECT:-}" ] && [ -n "${GOOGLE_CLOUD_PROJECT:-}" ]; then
    VERTEXAI_PROJECT="$GOOGLE_CLOUD_PROJECT"
  fi

  if [ -z "${VERTEXAI_PROJECT:-}" ] && command -v gcloud >/dev/null 2>&1; then
    local configured
    configured="$(gcloud config get-value project 2>/dev/null || true)"
    if [ -n "$configured" ] && [ "$configured" != "(unset)" ]; then
      VERTEXAI_PROJECT="$configured"
    fi
  fi

  if [ -z "${VERTEXAI_PROJECT:-}" ]; then
    VERTEXAI_PROJECT="$DEFAULT_VERTEX_PROJECT"
  fi

  VERTEXAI_LOCATION="${VERTEXAI_LOCATION:-$DEFAULT_VERTEX_LOCATION}"
  UV_CACHE_DIR="${UV_CACHE_DIR:-$DEFAULT_UV_CACHE_DIR}"

  export VERTEXAI_PROJECT
  export VERTEXAI_LOCATION
  export UV_CACHE_DIR
}

openhands_sync_gcloud_project() {
  command -v gcloud >/dev/null 2>&1 || return 0

  local configured
  configured="$(gcloud config get-value project 2>/dev/null || true)"
  if [ "$configured" != "$VERTEXAI_PROJECT" ]; then
    gcloud config set project "$VERTEXAI_PROJECT" >/dev/null
  fi
}
