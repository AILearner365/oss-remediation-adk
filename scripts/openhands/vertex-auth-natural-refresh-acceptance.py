#!/usr/bin/env python3
"""Live acceptance test for natural Vertex credential renewal in OpenHands.

The live path deliberately uses no mocks, forced expiry, explicit refresh, or
replacement credentials. It observes the credential cached by LiteLLM's actual
Vertex Gemini handler after a successful OpenHands request, waits until that
token's captured nominal expiry has naturally passed, and then sends a second
request through the same OpenHands LLM instance.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import re
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
DEFAULT_MODEL = "vertex_ai/gemini-2.5-flash"
BEARER_PATTERN = re.compile(r"(?i)(bearer\s+)[^\s,;]+")
SECRET_PATTERN = re.compile(
    r"(?i)((?:access[_ -]?token|refresh[_ -]?token|private[_ -]?key|"
    r"client[_ -]?secret)\s*[:=]\s*)[^\s,;]+"
)
AUTHORIZATION_PATTERN = re.compile(
    r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+"
)


class AcceptanceTimeout(RuntimeError):
    """The natural credential boundary was not reached within the time bound."""


class AcceptanceInterrupted(RuntimeError):
    """The process received a clean-interruption signal."""


class InstrumentationError(RuntimeError):
    """The credential used by LiteLLM could not be observed unambiguously."""


@dataclass
class WaitObservation:
    crossed_at: datetime
    polls: int


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime | None = None) -> str:
    return (value or utc_now()).astimezone(timezone.utc).isoformat()


def normalize_expiry(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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


def redact_text(value: str) -> str:
    """Redact common credential forms before any user-provided text is stored."""

    def replace(match: re.Match[str]) -> str:
        return match.group(1) + "[REDACTED]"

    value = AUTHORIZATION_PATTERN.sub(replace, value)
    value = BEARER_PATTERN.sub(replace, value)
    return SECRET_PATTERN.sub(replace, value)


def exception_metadata(exc: BaseException) -> dict[str, Any]:
    """Return allowlisted exception metadata, never the raw exception message."""

    chain: list[str] = []
    markers: set[str] = set()
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(f"{type(current).__module__}.{type(current).__name__}")
        text = str(current).lower()
        if "missing 'email' field" in text:
            markers.add("metadata-service-account-email-missing")
        if "permission" in text or "forbidden" in text:
            markers.add("permission-denied")
        if "timeout" in text or "timed out" in text:
            markers.add("timeout")
        current = current.__cause__ or current.__context__
    return {"exceptionTypes": chain, "errorMarkers": sorted(markers)}


def wait_for_natural_boundary(
    credentials: Any,
    *,
    token_expiry: datetime,
    expiry_grace_seconds: float,
    timeout_seconds: float,
    poll_seconds: float,
    interrupted: Callable[[], bool],
    monotonic: Callable[[], float] = time.monotonic,
    wall_clock: Callable[[], datetime] = utc_now,
    sleeper: Callable[[float], None] = time.sleep,
    on_poll: Callable[[float, bool, float], None] | None = None,
) -> WaitObservation:
    if timeout_seconds <= 0 or poll_seconds <= 0 or expiry_grace_seconds < 0:
        raise ValueError("timeout/poll must be positive and expiry grace non-negative")
    normalized_expiry = normalize_expiry(token_expiry)
    if normalized_expiry is None:
        raise ValueError("token expiry is required")
    boundary = normalized_expiry + timedelta(seconds=expiry_grace_seconds)
    deadline = monotonic() + timeout_seconds
    polls = 0
    while True:
        if interrupted():
            raise AcceptanceInterrupted("interrupted while waiting for refresh boundary")
        expired = bool(credentials.expired)
        polls += 1
        remaining = max(0.0, deadline - monotonic())
        seconds_until_boundary = (boundary - wall_clock()).total_seconds()
        if on_poll is not None:
            on_poll(remaining, expired, seconds_until_boundary)
        # google-auth's ``expired`` property becomes true at an early refresh
        # threshold. The acceptance boundary is the token's captured nominal
        # expiry, plus a small grace interval—not that proactive threshold.
        if seconds_until_boundary <= 0:
            return WaitObservation(crossed_at=wall_clock(), polls=polls)
        if remaining <= 0:
            raise AcceptanceTimeout("natural refresh boundary was not reached before timeout")
        sleeper(min(poll_seconds, remaining))


def classify_verdict(state: dict[str, Any]) -> str:
    if state.get("interrupted") or state.get("timedOut") or state.get("instrumentationFailed"):
        return "INCONCLUSIVE"
    required = (
        "initialRequestSucceeded",
        "boundaryCrossed",
        "originalTokenNominalExpiryCrossed",
        "postBoundaryRequestSucceeded",
        "sameLlmClient",
        "sameLiteLlmHandler",
        "sameCredentialObject",
        "tokenChanged",
        "expiryAdvanced",
        "postBoundaryCredentialValid",
    )
    if all(state.get(key) is True for key in required):
        return "PASS"
    return "FAIL"


def render_report(report: dict[str, Any]) -> str:
    """Render a secret-free, human-readable report."""

    state = report["state"]
    lines = [
        "# OpenHands Vertex natural credential refresh acceptance",
        "",
        f"- Started: `{report['startedAt']}`",
        f"- Completed: `{report.get('completedAt') or 'in progress'}`",
        f"- Verdict: **{report['verdict']}**",
        f"- Model: `{report['environment']['model']}`",
        f"- Project: `{report['environment']['project']}`",
        f"- Location: `{report['environment']['location']}`",
        "",
        "## Dependency versions",
        "",
    ]
    for name, version in report["environment"]["dependencies"].items():
        lines.append(f"- `{name}=={version}`")
    lines.extend(
        [
            "",
            "## Scenario and acceptance criteria",
            "",
            "One Python process creates one OpenHands `LLM`, completes a real Vertex request,",
            "observes the exact credential cached by LiteLLM, waits without model calls until",
            "the captured token's nominal expiry plus a grace interval, then completes a second request through",
            "the same `LLM`. PASS requires same-handler and same-credential identity, a changed",
            "in-memory token value (value never recorded), advanced expiry, valid post-boundary",
            "credentials, and both expected model responses.",
            "",
            "## Safe authentication observations",
            "",
        ]
    )
    for key in sorted(state):
        lines.append(f"- `{key}`: `{json.dumps(state[key], sort_keys=True)}`")
    lines.extend(["", "## Events", ""])
    for event in report["events"]:
        details = json.dumps(event.get("details", {}), sort_keys=True)
        lines.append(f"- `{event['timestamp']}` **{event['name']}** — `{details}`")
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- This is one natural refresh-boundary observation, not a guarantee for every future Cloud Shell session.",
            "- The test observes LiteLLM 1.104.2 internals pinned by OpenHands SDK 1.50.0; cache structure changes must fail closed.",
            "- Offline simulations validate instrumentation only and never count as live reliability evidence.",
            "",
        ]
    )
    return redact_text("\n".join(lines))


def persist_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(render_report(report), encoding="utf-8")
    temporary.replace(path)


def dependency_versions() -> dict[str, str]:
    versions = {}
    for name in ("openhands-sdk", "openhands-tools", "litellm", "google-auth"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "NOT_INSTALLED"
    return versions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=os.environ.get("VERTEXAI_PROJECT", ""))
    parser.add_argument("--location", default=os.environ.get("VERTEXAI_LOCATION", "us-central1"))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout-seconds", type=float, default=5400)
    parser.add_argument("--poll-seconds", type=float, default=15)
    parser.add_argument("--expiry-grace-seconds", type=float, default=5)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def run_live(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    if not args.project:
        raise ValueError("Vertex project is required via --project or VERTEXAI_PROJECT")

    import google.auth
    import litellm.main as litellm_main
    from openhands.sdk import LLM, Message, TextContent

    os.environ["VERTEXAI_PROJECT"] = args.project
    os.environ["VERTEXAI_LOCATION"] = args.location

    interrupted_flag = {"value": False}

    def handle_signal(signum: int, frame: Any) -> None:
        interrupted_flag["value"] = True

    for signal_name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signal_name, handle_signal)

    report: dict[str, Any] = {
        "startedAt": iso_utc(),
        "completedAt": None,
        "verdict": "INCONCLUSIVE",
        "environment": {
            "python": sys.version.split()[0],
            "model": args.model,
            "project": args.project,
            "location": args.location,
            "dependencies": dependency_versions(),
            "timeoutSeconds": args.timeout_seconds,
            "pollSeconds": args.poll_seconds,
            "expiryGraceSeconds": args.expiry_grace_seconds,
        },
        "state": {},
        "events": [],
    }
    state = report["state"]

    def event(name: str, **details: Any) -> None:
        report["events"].append({"timestamp": iso_utc(), "name": name, "details": details})
        persist_report(args.report, report)

    try:
        discovered, detected_project = google.auth.default(scopes=[CLOUD_PLATFORM_SCOPE])
        state.update(
            {
                "discoveredCredentialClass": f"{type(discovered).__module__}.{type(discovered).__name__}",
                "discoveredCredentialSource": credential_source(discovered),
                "discoveredProjectMatches": not detected_project or detected_project == args.project,
                "discoveredTokenPresent": bool(discovered.token),
                "discoveredValid": bool(discovered.valid),
            }
        )
        event("ADC_DISCOVERED")

        handler = litellm_main.vertex_chat_completion
        mapping = handler._credentials_project_mapping
        cache_key = (None, args.project)
        if cache_key in mapping:
            raise InstrumentationError("LiteLLM credential cache was not empty at test start")

        llm = LLM(
            model=args.model,
            api_key=None,
            usage_id="vertex-natural-refresh-acceptance",
            num_retries=0,
        )
        llm_identity = id(llm)
        handler_identity = id(handler)
        first_marker = "VERTEX_NATURAL_REFRESH_INITIAL_OK"
        first_started = iso_utc()
        first = llm.completion(
            messages=[Message(role="user", content=[TextContent(text=f"Reply with exactly: {first_marker}")])]
        )
        first_text = "\n".join(c.text for c in first.message.content if isinstance(c, TextContent))
        state["initialRequestStartedAt"] = first_started
        state["initialRequestCompletedAt"] = iso_utc()
        state["initialRequestSucceeded"] = first_marker in first_text
        if not state["initialRequestSucceeded"]:
            raise RuntimeError("initial model response did not contain the expected marker")

        if cache_key not in mapping:
            raise InstrumentationError("expected LiteLLM Vertex credential cache entry was absent")
        entry = mapping[cache_key]
        credentials = entry[0] if isinstance(entry, tuple) else entry
        initial_token = credentials.token
        initial_expiry = normalize_expiry(getattr(credentials, "expiry", None))
        if not initial_token or initial_expiry is None:
            raise InstrumentationError("cached credential lacked token or expiry metadata")
        state.update(
            {
                "requestCredentialClass": f"{type(credentials).__module__}.{type(credentials).__name__}",
                "requestCredentialSource": credential_source(credentials),
                "discoveryAndRequestCredentialSameObject": discovered is credentials,
                "initialRefreshSucceeded": bool(credentials.valid),
                "initialCredentialValid": bool(credentials.valid),
                "initialCredentialExpiryUtc": iso_utc(initial_expiry),
                "initialCredentialLifetimeSeconds": int((initial_expiry - utc_now()).total_seconds()),
                "initialTokenPresent": True,
            }
        )
        event("INITIAL_MODEL_REQUEST_SUCCEEDED")

        last_progress_bucket = None

        def on_poll(
            remaining: float, expired: bool, seconds_until_boundary: float
        ) -> None:
            nonlocal last_progress_bucket
            bucket = int(remaining // 300)
            if bucket != last_progress_bucket or expired:
                last_progress_bucket = bucket
                event(
                    "WAITING_FOR_NATURAL_BOUNDARY",
                    timeoutRemainingSeconds=int(remaining),
                    credentialExpired=expired,
                    secondsUntilNominalExpiry=int(
                        (initial_expiry - utc_now()).total_seconds()
                    ),
                    secondsUntilAcceptanceBoundary=int(seconds_until_boundary),
                )

        observation = wait_for_natural_boundary(
            credentials,
            token_expiry=initial_expiry,
            expiry_grace_seconds=args.expiry_grace_seconds,
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
            interrupted=lambda: interrupted_flag["value"],
            on_poll=on_poll,
        )
        state["boundaryCrossed"] = True
        state["originalTokenNominalExpiryCrossed"] = True
        state["boundaryCrossedAt"] = iso_utc(observation.crossed_at)
        state["boundaryPollCount"] = observation.polls
        state["expiredPropertyAtBoundary"] = bool(credentials.expired)
        event("NATURAL_REFRESH_BOUNDARY_CROSSED")

        second_marker = "VERTEX_NATURAL_REFRESH_POST_BOUNDARY_OK"
        second_started = iso_utc()
        second = llm.completion(
            messages=[Message(role="user", content=[TextContent(text=f"Reply with exactly: {second_marker}")])]
        )
        second_text = "\n".join(c.text for c in second.message.content if isinstance(c, TextContent))
        current_handler = litellm_main.vertex_chat_completion
        current_mapping = current_handler._credentials_project_mapping
        current_entry = current_mapping.get(cache_key)
        if current_entry is None:
            raise InstrumentationError(
                "LiteLLM credential cache entry disappeared after the boundary request"
            )
        current_credentials = (
            current_entry[0] if isinstance(current_entry, tuple) else current_entry
        )
        post_expiry = normalize_expiry(getattr(current_credentials, "expiry", None))
        state.update(
            {
                "postBoundaryRequestStartedAt": second_started,
                "postBoundaryRequestCompletedAt": iso_utc(),
                "postBoundaryRequestSucceeded": second_marker in second_text,
                "sameLlmClient": id(llm) == llm_identity,
                "sameLiteLlmHandler": id(current_handler) == handler_identity,
                "sameCredentialObject": current_credentials is credentials,
                "tokenChanged": bool(current_credentials and current_credentials.token != initial_token),
                "expiryAdvanced": bool(post_expiry and post_expiry > initial_expiry),
                "expiryAdvancedSeconds": (
                    int((post_expiry - initial_expiry).total_seconds()) if post_expiry else None
                ),
                "postBoundaryCredentialExpiryUtc": iso_utc(post_expiry) if post_expiry else None,
                "postBoundaryCredentialValid": bool(current_credentials and current_credentials.valid),
                "postBoundaryTokenPresent": bool(current_credentials and current_credentials.token),
                "naturalRenewalEstablished": bool(
                    current_credentials is credentials
                    and current_credentials.token != initial_token
                    and post_expiry
                    and post_expiry > initial_expiry
                ),
            }
        )
        event("POST_BOUNDARY_MODEL_REQUEST_COMPLETED")
    except AcceptanceInterrupted as exc:
        state["interrupted"] = True
        state["failure"] = exception_metadata(exc)
        event("TEST_INTERRUPTED")
    except AcceptanceTimeout as exc:
        state["timedOut"] = True
        state["failure"] = exception_metadata(exc)
        event("BOUNDARY_WAIT_TIMED_OUT")
    except InstrumentationError as exc:
        state["instrumentationFailed"] = True
        state["failure"] = exception_metadata(exc)
        event("INSTRUMENTATION_FAILED")
    except Exception as exc:
        state["failure"] = exception_metadata(exc)
        event("LIVE_TEST_FAILED")
    finally:
        report["completedAt"] = iso_utc()
        report["verdict"] = classify_verdict(state)
        persist_report(args.report, report)

    return report["verdict"], report


def main() -> int:
    args = parse_args()
    verdict, report = run_live(args)
    print(f"VERTEX_NATURAL_REFRESH_VERDICT={verdict}")
    print(f"VERTEX_NATURAL_REFRESH_REPORT={args.report}")
    print(f"INITIAL_MODEL_REQUEST={report['state'].get('initialRequestSucceeded', False)}")
    print(f"BOUNDARY_CROSSED={report['state'].get('boundaryCrossed', False)}")
    print(f"NATURAL_RENEWAL_ESTABLISHED={report['state'].get('naturalRenewalEstablished', False)}")
    print(f"POST_BOUNDARY_MODEL_REQUEST={report['state'].get('postBoundaryRequestSucceeded', False)}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
