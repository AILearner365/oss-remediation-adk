"""Regression tests for the Task-13 metadata credential failure mechanism.

These tests do not contact Google or expose credentials. They exercise the real
Google Auth credential class and, when installed, the pinned LiteLLM/OpenHands
classes with a deterministic malformed metadata response.
"""

from __future__ import annotations

import importlib.util
import unittest
from datetime import UTC, datetime, timedelta
from unittest import mock

from google.auth import exceptions
from google.auth.compute_engine import _metadata
from google.auth.compute_engine.credentials import Credentials


PROJECT = "auth-regression.invalid"
MISSING_EMAIL = "service account info is missing 'email' field"


def metadata_without_email(*args, **kwargs):
    """Return the malformed shape observed from the Cloud Shell metadata path."""

    return {"scopes": ["https://www.googleapis.com/auth/cloud-platform"]}


class GoogleAuthFailureMechanismTests(unittest.TestCase):
    def test_compute_credential_rejects_metadata_info_without_email(self):
        credentials = Credentials()

        with mock.patch.object(
            _metadata, "get_service_account_info", side_effect=metadata_without_email
        ):
            with self.assertRaisesRegex(exceptions.RefreshError, MISSING_EMAIL):
                credentials.refresh(object())


@unittest.skipUnless(importlib.util.find_spec("litellm"), "LiteLLM is not installed")
class LiteLLMFailureMechanismTests(unittest.TestCase):
    def test_cached_token_succeeds_then_expired_token_hits_missing_email(self):
        from litellm.llms.vertex_ai.vertex_llm_base import VertexBase

        credentials = Credentials()
        credentials.token = "test-token-never-printed"
        credentials.expiry = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)
        vertex = VertexBase()
        cache_key = (None, PROJECT)
        vertex._credentials_project_mapping[cache_key] = (credentials, PROJECT)

        try:
            token, project = vertex.get_access_token(None, PROJECT)
            self.assertEqual("test-token-never-printed", token)
            self.assertEqual(PROJECT, project)

            credentials.expiry = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
            with mock.patch.object(
                _metadata, "get_service_account_info", side_effect=metadata_without_email
            ):
                with self.assertRaisesRegex(exceptions.RefreshError, MISSING_EMAIL):
                    vertex.get_access_token(None, PROJECT)
        finally:
            vertex._credentials_project_mapping.pop(cache_key, None)


@unittest.skipUnless(importlib.util.find_spec("openhands"), "OpenHands SDK is not installed")
class OpenHandsFailureMechanismTests(unittest.TestCase):
    def test_openhands_wraps_same_google_auth_refresh_failure(self):
        from litellm.llms.vertex_ai.vertex_llm_base import VertexBase
        from openhands.sdk import LLM, Message, TextContent
        from openhands.sdk.llm.exceptions import LLMServiceUnavailableError

        credentials = Credentials()
        with (
            mock.patch.object(
                VertexBase,
                "_credentials_from_default_auth",
                return_value=(credentials, PROJECT),
            ),
            mock.patch.object(
                _metadata, "get_service_account_info", side_effect=metadata_without_email
            ),
        ):
            llm = LLM(
                model="vertex_ai/gemini-2.5-flash",
                api_key=None,
                usage_id="auth-failure-mechanism-test",
                num_retries=0,
            )
            with self.assertRaises(LLMServiceUnavailableError) as raised:
                llm.completion(
                    messages=[
                        Message(
                            role="user",
                            content=[TextContent(text="This request must not reach Vertex")],
                        )
                    ]
                )

        self.assertIn(MISSING_EMAIL, str(raised.exception))
        cause_names = []
        current = raised.exception
        seen = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            cause_names.append(type(current).__name__)
            current = current.__cause__ or current.__context__
        self.assertIn("RefreshError", cause_names)


if __name__ == "__main__":
    unittest.main()
