"""Offline regression checks for recovery-aware independent validation.

The original baseline cannot silently become a new task's evidence: recovery
must bind provenance and compare the original immutable source artifacts.
"""
from inspect import getsource
import unittest
from openhands_shared.validation import SharedValidationService


class RecoveryValidationContractTests(unittest.TestCase):
    def test_inherited_report_checks_original_provenance(self):
        source = getsource(SharedValidationService._verified_inputs)
        self.assertIn("request.correlation_id", source)
        self.assertIn('document.get("taskId") != original_id', source)
        self.assertIn("old_baseline.report_sha256 != baseline.report_sha256", source)
        self.assertIn("original_artifact.relative_path != baseline_artifact.relative_path", source)
        self.assertIn("old_request.repository != request.repository", source)
        self.assertIn("old_request.constraints != request.constraints", source)
        self.assertIn("self._verify_artifact(original_artifact)", source)

    def test_detached_recovery_clone_requires_exact_origin(self):
        source = getsource(SharedValidationService._verify_workspace)
        self.assertIn('["remote", "get-url", "origin"]', source)
        self.assertIn("Path(origin.strip()).resolve() != source.resolve()", source)
        self.assertIn("source_head.strip() != preparation.baseline_commit", source)
        self.assertIn("task workspace belongs to another repository", source)


if __name__ == "__main__":
    unittest.main()
