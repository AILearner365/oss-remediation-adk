from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from autonomous_oss_remediation_agent.config import (
    ConstraintSpec,
    RemediationRequest,
    SpringBootVersionPolicy,
)
from autonomous_oss_remediation_agent.deterministic.constraints import ConstraintEvaluator
from autonomous_oss_remediation_agent.models import RepositoryBaseline
from autonomous_oss_remediation_agent.prompt import initial_message


class AutonomousSpringBootPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repository = Path(self.temp.name)
        self.evaluator = ConstraintEvaluator()

    def tearDown(self):
        self.temp.cleanup()

    def test_default_policy_allows_patch_and_minor_but_rejects_major_and_downgrade(self):
        cases = (
            ("3.5.1", "patch", True),
            ("3.6.0", "minor", True),
            ("4.0.0", "major", False),
            ("3.4.9", "downgrade", False),
            ("3.5.0", "unchanged", True),
        )
        for final_version, change_type, expected in cases:
            with self.subTest(final_version=final_version):
                check = self._validate("3.5.0", final_version, ConstraintSpec())
                self.assertEqual(expected, check.passed)
                self.assertEqual(change_type, check.evidence["detected_change_type"])

    def test_explicit_approved_version_allows_only_that_major_target(self):
        policy = SpringBootVersionPolicy(approved_versions=("4.0.7",))
        approved = self._validate(
            "3.5.0",
            "4.0.7",
            ConstraintSpec(spring_boot_version_policy=policy),
        )
        unapproved = self._validate(
            "3.5.0",
            "4.1.0",
            ConstraintSpec(spring_boot_version_policy=policy),
        )
        self.assertTrue(approved.passed)
        self.assertFalse(unapproved.passed)

    def test_approved_versions_do_not_silently_allow_downgrades(self):
        policy = SpringBootVersionPolicy(approved_versions=("3.4.9",))
        check = self._validate(
            "3.5.0",
            "3.4.9",
            ConstraintSpec(spring_boot_version_policy=policy),
        )
        self.assertFalse(check.passed)
        self.assertEqual("downgrade", check.evidence["detected_change_type"])

    def test_required_version_forces_exact_final_version(self):
        policy = SpringBootVersionPolicy(required_version="4.0.7")
        required = self._validate(
            "3.5.0",
            "4.0.7",
            ConstraintSpec(spring_boot_version_policy=policy),
        )
        other = self._validate(
            "3.5.0",
            "3.6.0",
            ConstraintSpec(spring_boot_version_policy=policy),
        )
        self.assertTrue(required.passed)
        self.assertFalse(other.passed)

    def test_legacy_protected_version_remains_an_exact_required_version(self):
        allowed = self._validate(
            "3.5.0",
            "4.0.7",
            ConstraintSpec(protected_spring_boot_version="4.0.7"),
        )
        rejected = self._validate(
            "3.5.0",
            "4.0.8",
            ConstraintSpec(protected_spring_boot_version="4.0.7"),
        )
        self.assertTrue(allowed.passed)
        self.assertFalse(rejected.passed)
        self.assertEqual(
            "protected_spring_boot_version",
            allowed.evidence["applicable_policy"]["source"],
        )

    def test_config_serialization_includes_spring_boot_policy(self):
        request = RemediationRequest.from_dict(
            {
                "repositoryUrl": "https://example.test/repo.git",
                "constraints": {
                    "version_policies": {
                        "spring_boot": {
                            "allow_patch": True,
                            "allow_minor": True,
                            "allow_major": False,
                            "allow_downgrade": False,
                            "approved_versions": ["4.0.7"],
                            "required_version": None,
                        }
                    }
                },
            }
        )
        serialized = request.to_dict()["constraints"]["version_policies"]["spring_boot"]
        self.assertEqual(["4.0.7"], serialized["approved_versions"])
        self.assertTrue(serialized["allow_minor"])
        self.assertFalse(serialized["allow_major"])

    def test_agent_context_contains_spring_boot_policy(self):
        request = RemediationRequest.from_dict(
            {
                "repositoryUrl": "https://example.test/repo.git",
                "constraints": {
                    "version_policies": {
                        "spring_boot": {
                            "allow_major": False,
                            "approved_versions": ["4.0.7"],
                        }
                    }
                },
            }
        )
        baseline = Mock(spec=RepositoryBaseline)
        baseline.to_dict.return_value = {
            "constraints": {"springBootVersions": ["parent=3.5.0"]}
        }

        message = initial_message(request, baseline)

        self.assertIn('"spring_boot"', message)
        self.assertIn('"approved_versions": [', message)
        self.assertIn('"4.0.7"', message)

    def test_unparseable_version_change_fails_closed(self):
        check = self._validate("3.5.0", "4.0.0-RC1", ConstraintSpec())
        self.assertFalse(check.passed)
        self.assertEqual("unparseable", check.evidence["detected_change_type"])

    def _validate(self, baseline_version: str, final_version: str, spec: ConstraintSpec):
        self._write_pom(baseline_version)
        baseline = self.evaluator.capture(self.repository)
        self._write_pom(final_version)
        checks = self.evaluator.validate(self.repository, baseline, spec, (), "")
        return next(check for check in checks if check.name == "spring_boot_version_policy")

    def _write_pom(self, version: str) -> None:
        (self.repository / "pom.xml").write_text(
            "<project><parent><groupId>org.springframework.boot</groupId>"
            "<artifactId>spring-boot-starter-parent</artifactId>"
            f"<version>{version}</version></parent></project>",
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
