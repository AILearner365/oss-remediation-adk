"""Offline assertions on retained REAL backend output; no backend/model execution.

The original experiment is documented in the readiness review. These tests prove
artifact consistency, not deployment wiring through the P0-blocked adapter.
"""
import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/p1-verification-20261020"


def read(path):
    return json.loads(path.read_text())


def tgf_packages(path):
    nodes = path.read_text().split("#", 1)[0].splitlines()
    result = set()
    for node in nodes:
        parts = node.split(" ", 1)[1].split(":")
        if len(parts) == 5 and parts[-1] in ("compile", "runtime"):
            result.add((":".join(parts[:2]), parts[3]))
    return result


class RetainedBackendEvidenceTests(unittest.TestCase):
    def test_retained_raw_evidence_hashes(self):
        for line in (EVIDENCE / "SHA256SUMS").read_text().splitlines():
            sha, name = line.split("  ", 1)
            self.assertEqual(hashlib.sha256((EVIDENCE / name).read_bytes()).hexdigest(), sha, name)

    def test_actual_profiled_resolution_matches_sbom_and_scanner_input(self):
        result = read(EVIDENCE / "backend/result.json")
        self.assertEqual(result["schema_version"], "1.0")
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["errors"], [])
        execution = result["execution"]
        self.assertEqual(execution["profiles"], ["intelligence-fixture"])
        self.assertEqual(execution["scopes"], ["compile", "runtime"])
        self.assertEqual(execution["release_selection"]["resolved_candidates"], ["3.3.1"])
        self.assertTrue(execution["original_project_unchanged"])
        fixture = ROOT / "tests_native/fixtures/sbri-profile/pom.xml"
        self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(),
                         result["application"]["original_pom_sha256"])
        for version in ("3.3.0", "3.3.1"):
            directory = EVIDENCE / "backend/evidence" / version
            resolved = tgf_packages(directory / "dependency-tree.tgf")
            sbom = read(directory / "inventory.cdx.json")
            components = {(c["group"] + ":" + c["name"], c["version"]) for c in sbom["components"]}
            reported = {(d["coordinate"], d["selected_version"]) for d in result["dependencies"]
                        if d["release"] == version}
            self.assertEqual(resolved, components)
            self.assertEqual(resolved, reported)
            self.assertEqual(len(resolved), 11)
            self.assertIn(("org.apache.commons:commons-text", "1.12.0"), resolved)
            self.assertIn(("org.springframework.boot:spring-boot", version), resolved)
            self.assertIn("found 11 packages", (directory / "scanner.log").read_text())
            scanner = read(directory / "scanner.json")
            # Scanner output omits nonvulnerable packages; never infer zero findings
            # or exact coverage from the count of packages in this response alone.
            self.assertTrue(scanner["results"])
            self.assertTrue(any(d["findings"] for d in result["dependencies"] if d["release"] == version))
        self.assertNotIn(("org.apache.commons:commons-text", "1.12.0"),
                         tgf_packages(EVIDENCE / "profile-disabled.tgf"))
        self.assertIn("not present in authoritative Maven metadata",
                      (EVIDENCE / "invalid-release.stderr").read_text())

    def test_result_matches_retained_backend_schema(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("Schema validator available in pinned SDK environment")
        jsonschema.Draft202012Validator(read(EVIDENCE / "result-schema-v1.json")).validate(
            read(EVIDENCE / "backend/result.json"))


if __name__ == "__main__":
    unittest.main()
