import base64
import io
import unittest
from email.message import Message
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from autonomous_oss_remediation_agent.capabilities.research import HttpResearchProvider, ResearchStatus


class Response(io.BytesIO):
    def __init__(self, body, media="text/html", status=200):
        super().__init__(body)
        self.headers = Message()
        self.headers["Content-Type"] = media
        self.status = status

    def geturl(self):
        return "https://example.test/final"


class ResearchAcquisitionTests(unittest.TestCase):
    def acquire(self, response, *, search=False, limit=2_000_000):
        opener = Mock()
        if isinstance(response, Exception):
            opener.open.side_effect = response
        else:
            opener.open.return_value = response
        with patch("autonomous_oss_remediation_agent.capabilities.research.socket.getaddrinfo",
                   return_value=[(None, None, None, None, ("93.184.215.14", 443))]), \
             patch("autonomous_oss_remediation_agent.capabilities.research.build_opener", return_value=opener):
            provider = HttpResearchProvider(enabled=True, max_response_bytes=limit)
            result = provider.search("release information") if search else provider.fetch("https://example.test/start")
        self.assertEqual(1, opener.open.call_count)  # No challenge bypass or hidden provider fallback.
        return result

    def test_challenge_is_blocked_for_search_and_fetch_with_raw_provenance(self):
        body = b'<form id="challenge-form" action="/anomaly.js">Please complete the challenge to confirm this search was made by a human.</form>'
        for search in (True, False):
            with self.subTest(search=search):
                result = self.acquire(Response(body), search=search)
                self.assertEqual(ResearchStatus.BLOCKED, result.status)
                self.assertEqual("BOT_CHALLENGE", result.failure_code)
                self.assertEqual((), result.results)
                self.assertEqual("", result.content)
                self.assertTrue(result.acquisition_succeeded)
                self.assertEqual(body, base64.b64decode(result.raw_bytes_b64))
                self.assertEqual("https://example.test/final", result.source)
                self.assertIn("Do not retry", result.recovery)

    def test_large_style_and_script_prefix_does_not_hide_body_within_default_bound(self):
        body = (b"<html><head><style>" + b"x" * 120_000 + b"</style><script>" + b"y" * 120_000
                + b"</script></head><body>Current release facts</body></html>")
        result = self.acquire(Response(body))
        self.assertEqual(ResearchStatus.SUCCESS, result.status)
        self.assertEqual("Current release facts", result.content)
        self.assertFalse(result.truncated)
        self.assertEqual(len(body), result.acquired_bytes)
        self.assertEqual(2_000_000, result.byte_limit)
        self.assertEqual(body, base64.b64decode(result.raw_bytes_b64))

    def test_limit_before_body_is_explicit_and_retained_prefix_is_not_full_source(self):
        result = self.acquire(Response(b"<style>" + b"x" * 1200 + b"</style><p>missing tail</p>"), limit=1000)
        self.assertEqual(ResearchStatus.SOURCE_TRUNCATED, result.status)
        self.assertEqual("SOURCE_LIMIT_BEFORE_USABLE_CONTENT", result.failure_code)
        self.assertTrue(result.truncated)
        self.assertEqual(1000, len(base64.b64decode(result.raw_bytes_b64)))
        self.assertIn("missing tail", result.recovery)

    def test_partial_useful_text_is_success_with_explicit_incompleteness(self):
        result = self.acquire(Response(b"<p>Useful fact</p><style>" + b"x" * 1200), limit=1000)
        self.assertEqual(ResearchStatus.SUCCESS, result.status)
        self.assertEqual("Useful fact", result.content)
        self.assertTrue(result.truncated)
        self.assertIn("source prefix", result.recovery)

    def test_http_denial_and_acquisition_failure_are_not_empty_successes(self):
        for code, expected in ((403, ResearchStatus.BLOCKED), (429, ResearchStatus.BLOCKED),
                               (503, ResearchStatus.HTTP_NETWORK_FAILURE)):
            with self.subTest(code=code):
                headers = Message()
                headers["Content-Type"] = "text/html"
                result = self.acquire(HTTPError("https://example.test/start", code, "error", headers, io.BytesIO(b"Unavailable")))
                self.assertEqual(expected, result.status)
                self.assertEqual(code, result.http_status)
                self.assertFalse(result.acquisition_succeeded)
                self.assertTrue(result.raw_bytes_b64)
                self.assertEqual("", result.content)
        network = self.acquire(URLError("offline"))
        self.assertEqual(ResearchStatus.HTTP_NETWORK_FAILURE, network.status)
        self.assertFalse(network.raw_bytes_b64)

    def test_unrecognized_search_response_remains_extraction_failure(self):
        result = self.acquire(Response(b"<html><p>Unexpected response</p></html>"), search=True)
        self.assertEqual(ResearchStatus.EXTRACTION_FAILURE, result.status)
        self.assertIn("not evidence of absence", result.recovery)

    def test_supported_search_still_extracts_results(self):
        result = self.acquire(Response(b'<a class="result__a" href="https://example.test/docs">Official docs</a>'), search=True)
        self.assertEqual(ResearchStatus.SUCCESS, result.status)
        self.assertEqual("Official docs", result.results[0]["title"])
        self.assertEqual("", result.content)
