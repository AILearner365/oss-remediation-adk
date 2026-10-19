"""Optional browser journey; install Playwright in /tmp and set PLAYWRIGHT_MODULE."""
import os
from pathlib import Path
import subprocess
import threading
import unittest
from wsgiref.simple_server import make_server

from tests.integration import test_openhands_product as fixtures


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "temporary Playwright module not configured")
class BrowserJourney(unittest.TestCase):
    def test_ui_submits_and_authorizes_the_same_offline_backend(self):
        fixture = fixtures.ProductJourneys("test_auth_input_boundary_and_no_implicit_execution")
        fixture.setUp()
        try:
            key = fixture.root / "browser-key"
            key.write_text(fixture.key)
            with make_server("127.0.0.1", 0, fixture.api) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                fixture.product.start()
                try:
                    result = subprocess.run([os.environ.get("PLAYWRIGHT_NODE", "node"),
                        str(Path(__file__).resolve().parents[1] / "js/openhands_product_browser.cjs")],
                        env={**os.environ, "REMEDIATION_BROWSER_KEY_FILE": str(key),
                            "REMEDIATION_BROWSER_URL": f"http://127.0.0.1:{server.server_port}",
                            "REMEDIATION_BROWSER_FAKE_ONLY": "1"},
                        capture_output=True, text=True, timeout=90)
                    self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                    fixture.product.wake.set()
                    self.assertTrue(fixture.native.run_calls <= 1)
                    self.assertEqual(len(fixture.product.tasks()), 1)
                finally:
                    server.shutdown()
                    thread.join()
        finally:
            fixture.tearDown()


if __name__ == "__main__":
    unittest.main()
