"""Offline tests for POC2 mock endpoint and synthetic hook contract."""
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import openhands_native_hook_poc as poc


class NativeHookPocTests(unittest.TestCase):
    def test_fail_closed_hook_protocol_and_local_model_feedback(self):
        original = poc.STATE
        try:
            with tempfile.TemporaryDirectory() as td:
                poc.STATE = Path(td)
                poc.save(poc.STATE / "verdict.json", {"accepted": False})
                self.assertEqual(poc.hook_cli(), 2)
                poc.save(poc.STATE / "verdict.json", {"accepted": True})
                self.assertEqual(poc.hook_cli(), 0)
                self.assertEqual([x["accepted"] for x in poc.json_file(
                    poc.STATE / "hooks.json", [])], [False, True])
                http = ThreadingHTTPServer(("127.0.0.1", 0), poc.MockLLM)
                thread = threading.Thread(target=http.serve_forever, daemon=True)
                thread.start()
                try:
                    for i in (1, 2):
                        conn = http.client.HTTPConnection("127.0.0.1", http.server_port)
                        text = poc.MARKER if i == 2 else "first finish"
                        payload = {
                            "model": "gpt-4o-mini",
                            "messages": [{"role": "user", "content": text}],
                            "tools": [{"type": "function", "function": {
                                "name": "finish", "parameters": {"type": "object"}
                            }}],
                        }
                        conn.request("POST", "/v1/chat/completions", json.dumps(payload),
                                     {"Content-Type": "application/json"})
                        res = conn.getresponse()
                        self.assertEqual(res.status, 200)
                        body = json.loads(res.read())
                        self.assertEqual(body["choices"][0]["message"]["tool_calls"][0]
                                         ["function"]["name"], "finish")
                        conn.close()
                    calls = poc.json_file(poc.STATE / "model-requests.json", [])
                    self.assertEqual([c["feedbackSeen"] for c in calls], [False, True])
                finally:
                    http.shutdown()
                    http.server_close()
        finally:
            poc.STATE = original

    def test_fixture_is_not_real_validation(self):
        self.assertNotEqual(poc.MARKER, "")
        self.assertEqual(poc.json_file(Path("/does-not-exist-poc2"), {}), {})


if __name__ == "__main__":
    unittest.main()
