"""Offline, synthetic contract checks for future Spring Boot release intelligence probes.

These do not call live APIs or assert that real candidate releases fix CVEs.
"""
import json
import unittest
from pathlib import Path


FIXTURE = Path(__file__).parent / "fixtures" / "spring_boot_release_intelligence_cases.json"


def classify(finding, candidate):
    """A deliberately tiny evidence-based contract, not the production resolver."""
    if candidate.get("application_override") is not None:
        if candidate.get("advisory_explicitly_affected") is True:
            return "still_affected"
        return "application_controlled"
    if not candidate.get("selected_version") or not candidate.get("selection_path"):
        return "unknown"
    if candidate.get("advisory_explicitly_affected") is True:
        return "still_affected"
    if candidate.get("advisory_explicitly_unaffected") is True:
        return "addressed_by_candidate_default_graph"
    return "unknown"


class SpringBootReleaseIntelligenceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]

    def test_four_cases_have_distinct_scenarios(self):
        self.assertEqual({c["id"] for c in self.cases}, {"C1", "C2", "C3", "C4"})

    def test_synthetic_scenarios_match_expected_classification(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                self.assertEqual(classify(case["finding"], case["candidate"]), case["expected"])

    def test_unknown_fixed_version_is_not_automatically_resolved(self):
        c = next(c for c in self.cases if c["id"] == "C3")
        self.assertIsNone(c["finding"]["fixed"])
        self.assertEqual(classify(c["finding"], c["candidate"]), "unknown")

    def test_managed_version_without_resolved_path_is_not_proof(self):
        c = next(c for c in self.cases if c["id"] == "C1")
        candidate = dict(c["candidate"], selection_path=None)
        self.assertEqual(classify(c["finding"], candidate), "unknown")

    def test_disappearing_path_is_not_proof_of_application_fix(self):
        c = next(c for c in self.cases if c["id"] == "C2")
        candidate = dict(c["candidate"], selection_path=None)
        self.assertEqual(classify(c["finding"], candidate), "unknown")

    def test_explicit_advisory_affected_overrides_version_number(self):
        c = next(c for c in self.cases if c["id"] == "C2")
        candidate = dict(c["candidate"], advisory_explicitly_unaffected=False, advisory_explicitly_affected=True)
        self.assertEqual(classify(c["finding"], candidate), "still_affected")


if __name__ == "__main__":
    unittest.main()
