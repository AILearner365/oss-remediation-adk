"""Focused tests for the host-side Vertex ADC refresh preflight."""

from __future__ import annotations

import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = ROOT / "scripts/openhands/vertex-adc-preflight.py"
POC_SCRIPT = ROOT / "scripts/openhands/openhands-cloudshell-poc.sh"


def load_preflight():
    spec = importlib.util.spec_from_file_location("vertex_adc_preflight", PREFLIGHT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {PREFLIGHT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeCredentials:
    __module__ = "google.auth.compute_engine.credentials"

    def __init__(self):
        self.token = None
        self.valid = False
        self.expiry = None
        self.service_account_email = "present-but-never-reported"
        self.refreshes = 0

    def refresh(self, request):
        self.refreshes += 1
        self.token = "secret-access-token"
        self.valid = True
        self.expiry = datetime.now(timezone.utc) + timedelta(hours=1)


class OpenHandsVertexAdcTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preflight = load_preflight()

    def test_preflight_forces_two_refreshes_without_returning_token_value(self):
        credentials = FakeCredentials()
        report = self.preflight.verify_adc(
            "project-a",
            default_provider=lambda **kwargs: (credentials, "project-a"),
            request_factory=object,
        )
        self.assertEqual(2, credentials.refreshes)
        self.assertEqual("metadata-server", report["credentialSource"])
        self.assertTrue(report["tokenPresent"])
        self.assertNotIn(credentials.token, repr(report))
        self.assertNotIn(credentials.service_account_email, repr(report))

    def test_project_mismatch_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "ADC project mismatch"):
            self.preflight.verify_adc(
                "project-a",
                default_provider=lambda **kwargs: (FakeCredentials(), "project-b"),
                request_factory=object,
            )

    def test_refresh_failure_reports_source_without_cause_message(self):
        class BrokenCredentials(FakeCredentials):
            __module__ = "google.auth.compute_engine.credentials"

            def refresh(self, request):
                raise RuntimeError("sensitive-provider-message")

        with self.assertRaises(self.preflight.AdcRefreshError) as raised:
            self.preflight.verify_adc(
                "project-a",
                default_provider=lambda **kwargs: (BrokenCredentials(), "project-a"),
                request_factory=object,
            )
        self.assertEqual("metadata-server", raised.exception.source)
        self.assertEqual("builtins.RuntimeError", raised.exception.cause_type)
        self.assertNotIn("sensitive-provider-message", str(raised.exception))

    def test_poc_uses_preflight_and_three_sequential_model_requests(self):
        script = POC_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("verify_vertex_adc_refresh", script)
        self.assertIn("range(1, 4)", script)
        self.assertNotIn("gcloud auth application-default print-access-token", script)
        execute = (ROOT / "scripts/openhands/openhands-gate2-execute.sh").read_text()
        self.assertLess(
            execute.index("openhands_verify_vertex_adc"),
            execute.index('git -C "$SOURCE_REPO" fetch'),
        )


if __name__ == "__main__":
    unittest.main()
