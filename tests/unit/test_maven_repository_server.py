"""Tests for the dependency-free local Maven repository facade."""

from __future__ import annotations

import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from maven_repository_server import serve_maven_repository


class MavenRepositoryServerTests(unittest.TestCase):
    def test_serves_existing_artifact_and_records_missing_resource(self):
        with tempfile.TemporaryDirectory() as tmp:
            repository = Path(tmp)
            artifact = repository / "org/example/demo/1.0/demo-1.0.pom"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("<project/>", encoding="utf-8")

            with serve_maven_repository((repository,)) as (url, requests):
                with urllib.request.urlopen(url + "org/example/demo/1.0/demo-1.0.pom") as response:
                    self.assertEqual(b"<project/>", response.read())
                with self.assertRaises(urllib.error.HTTPError) as missing:
                    urllib.request.urlopen(url + "org/example/missing/1.0/missing-1.0.pom")
                self.assertEqual(404, missing.exception.code)

            self.assertEqual([True, False], [request["found"] for request in requests])
            with self.assertRaises(urllib.error.URLError):
                urllib.request.urlopen(url, timeout=1)

    def test_rejects_missing_repository_before_starting_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing"
            with self.assertRaisesRegex(ValueError, "Maven repository is unavailable"):
                with serve_maven_repository((missing,)):
                    self.fail("server should not start")


if __name__ == "__main__":
    unittest.main()
