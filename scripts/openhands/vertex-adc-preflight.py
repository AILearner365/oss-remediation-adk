#!/usr/bin/env python3
"""Validate the Python ADC path used by LiteLLM without exposing tokens."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any, Callable


CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


class AdcRefreshError(RuntimeError):
    def __init__(self, source: str, credential_class: str, cause: Exception):
        super().__init__("Python ADC explicit refresh failed")
        self.source = source
        self.credential_class = credential_class
        self.cause_type = f"{type(cause).__module__}.{type(cause).__name__}"


def credential_source(credentials: Any) -> str:
    module = type(credentials).__module__
    if module.startswith("google.auth.compute_engine"):
        return "metadata-server"
    if module.startswith("google.oauth2.credentials"):
        return "authorized-user-adc"
    if module.startswith("google.oauth2.service_account"):
        return "service-account-adc"
    if "identity_pool" in module or "external_account" in module:
        return "federated-adc"
    return module


def verify_adc(
    expected_project: str,
    *,
    refresh_count: int = 2,
    default_provider: Callable[..., tuple[Any, str | None]] | None = None,
    request_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    if refresh_count < 2:
        raise ValueError("At least two explicit refreshes are required")
    if default_provider is None or request_factory is None:
        import google.auth
        from google.auth.transport.requests import Request

        default_provider = default_provider or google.auth.default
        request_factory = request_factory or Request

    credentials, detected_project = default_provider(scopes=[CLOUD_PLATFORM_SCOPE])
    source = credential_source(credentials)
    try:
        for _ in range(refresh_count):
            credentials.refresh(request_factory())
    except Exception as exc:
        raise AdcRefreshError(source, type(credentials).__name__, exc) from exc

    if not credentials.token or not credentials.valid:
        raise RuntimeError("ADC refresh completed without a valid access token")
    if detected_project and detected_project != expected_project:
        raise RuntimeError(
            f"ADC project mismatch: expected {expected_project}, detected {detected_project}"
        )

    expiry = getattr(credentials, "expiry", None)
    if expiry is None:
        raise RuntimeError("ADC refresh returned credentials without an expiry")
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    remaining_seconds = int((expiry - datetime.now(timezone.utc)).total_seconds())
    if remaining_seconds < 300:
        raise RuntimeError("ADC refresh returned credentials expiring in under five minutes")

    return {
        "credentialSource": source,
        "credentialClass": type(credentials).__name__,
        "detectedProject": detected_project,
        "effectiveProject": expected_project,
        "explicitRefreshes": refresh_count,
        "expiryPresent": True,
        "minimumLifetimeSatisfied": True,
        "principalMetadataPresent": bool(
            getattr(credentials, "service_account_email", None)
        ),
        "tokenPresent": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Force-refresh Python ADC using the pinned OpenHands runtime."
    )
    parser.add_argument("--expected-project", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = verify_adc(args.expected_project)
    except Exception as exc:
        print("VERTEX_ADC_REFRESH=FAIL")
        print(f"VERTEX_ADC_ERROR_TYPE={type(exc).__module__}.{type(exc).__name__}")
        if isinstance(exc, AdcRefreshError):
            print(f"VERTEX_ADC_SOURCE={exc.source}")
            print(f"VERTEX_ADC_CREDENTIAL_CLASS={exc.credential_class}")
            print(f"VERTEX_ADC_CAUSE_TYPE={exc.cause_type}")
        print(
            "Cloud Shell ADC is not refreshable by the Python Google Auth path. "
            "Reauthorize or restart the Cloud Shell session before running OpenHands."
        )
        return 1

    # This report intentionally contains metadata only, never token values.
    print(json.dumps(report, sort_keys=True))
    print("VERTEX_ADC_REFRESH=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
