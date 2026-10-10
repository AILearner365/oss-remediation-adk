"""Offline tests for the natural-refresh acceptance-test instrumentation."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/openhands/vertex-auth-natural-refresh-acceptance.py"


def load_acceptance():
    spec = importlib.util.spec_from_file_location("vertex_auth_acceptance", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeClock:
    def __init__(self):
        self.value = 0.0
        self.started = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds

    def now(self):
        return self.started + timedelta(seconds=self.value)


class NaturalRefreshAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.acceptance = load_acceptance()

    def test_wait_uses_nominal_expiry_not_early_expired_property(self):
        clock = FakeClock()

        class Credentials:
            @property
            def expired(self):
                return clock.value >= 1

        result = self.acceptance.wait_for_natural_boundary(
            Credentials(),
            token_expiry=clock.started + timedelta(seconds=3),
            expiry_grace_seconds=1,
            timeout_seconds=10,
            poll_seconds=1,
            interrupted=lambda: False,
            monotonic=clock.monotonic,
            wall_clock=clock.now,
            sleeper=clock.sleep,
        )
        self.assertEqual(5, result.polls)
        self.assertEqual(4, clock.value)

    def test_wait_times_out_without_forcing_expiry(self):
        clock = FakeClock()

        class Credentials:
            expired = False

        with self.assertRaises(self.acceptance.AcceptanceTimeout):
            self.acceptance.wait_for_natural_boundary(
                Credentials(),
                token_expiry=clock.started + timedelta(seconds=20),
                expiry_grace_seconds=0,
                timeout_seconds=2,
                poll_seconds=1,
                interrupted=lambda: False,
                monotonic=clock.monotonic,
                wall_clock=clock.now,
                sleeper=clock.sleep,
            )
        self.assertEqual(2, clock.value)

    def test_interruption_stops_wait_cleanly(self):
        class Credentials:
            expired = False

        with self.assertRaises(self.acceptance.AcceptanceInterrupted):
            self.acceptance.wait_for_natural_boundary(
                Credentials(),
                token_expiry=datetime.now(timezone.utc) + timedelta(hours=1),
                expiry_grace_seconds=0,
                timeout_seconds=10,
                poll_seconds=1,
                interrupted=lambda: True,
            )

    def test_verdict_requires_boundary_identity_and_renewal_evidence(self):
        passing = {
            "initialRequestSucceeded": True,
            "boundaryCrossed": True,
            "originalTokenNominalExpiryCrossed": True,
            "postBoundaryRequestSucceeded": True,
            "sameLlmClient": True,
            "sameLiteLlmHandler": True,
            "sameCredentialObject": True,
            "tokenChanged": True,
            "expiryAdvanced": True,
            "postBoundaryCredentialValid": True,
        }
        self.assertEqual("PASS", self.acceptance.classify_verdict(passing))
        passing["tokenChanged"] = False
        self.assertEqual("FAIL", self.acceptance.classify_verdict(passing))
        passing["timedOut"] = True
        self.assertEqual("INCONCLUSIVE", self.acceptance.classify_verdict(passing))

    def test_report_redacts_secret_forms(self):
        text = self.acceptance.redact_text(
            "Authorization: Bearer abc.def access_token=tokvalue "
            "refresh-token: refreshvalue private_key=keyvalue client_secret: clientvalue"
        )
        for secret in ("abc.def", "tokvalue", "refreshvalue", "keyvalue", "clientvalue"):
            self.assertNotIn(secret, text)
        self.assertGreaterEqual(text.count("[REDACTED]"), 5)

    def test_exception_metadata_never_returns_raw_message(self):
        secret = "access_token=should-never-appear"
        metadata = self.acceptance.exception_metadata(RuntimeError(secret))
        self.assertNotIn(secret, repr(metadata))
        self.assertEqual(["builtins.RuntimeError"], metadata["exceptionTypes"])

    def test_report_contains_structured_acceptance_sections(self):
        report = {
            "startedAt": datetime.now(timezone.utc).isoformat(),
            "completedAt": None,
            "verdict": "INCONCLUSIVE",
            "environment": {
                "model": "vertex_ai/gemini-2.5-flash",
                "project": "project-a",
                "location": "us-central1",
                "dependencies": {"openhands-sdk": "1.50.0"},
            },
            "state": {"timedOut": True},
            "events": [],
        }
        rendered = self.acceptance.render_report(report)
        self.assertIn("Scenario and acceptance criteria", rendered)
        self.assertIn("Safe authentication observations", rendered)
        self.assertIn("Verdict: **INCONCLUSIVE**", rendered)

    def test_live_implementation_does_not_force_refresh_or_mock_google_auth(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("credentials.refresh(", source)
        self.assertNotIn("unittest.mock", source)
        self.assertNotIn("credentials.expiry =", source)
        self.assertIn("token_expiry=initial_expiry", source)


if __name__ == "__main__":
    unittest.main()
