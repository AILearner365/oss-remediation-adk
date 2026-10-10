"""Focused regression tests for Task-10 findings; no model or network calls."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from autonomous_oss_remediation_agent.deterministic.constraints import (
    _classify_version_change,
    _spring_boot_change_allowed,
)
from autonomous_oss_remediation_agent.config import SpringBootVersionPolicy


ROOT = Path(__file__).resolve().parents[2]


class Gate2FeedbackIntegrityTests(unittest.TestCase):
    def test_stable_patch_and_minor_upgrade_are_classified(self):
        self.assertEqual("patch", _classify_version_change("4.0.6", "4.0.8"))
        self.assertEqual("minor", _classify_version_change("4.0.6", "4.1.1"))

    def test_prerelease_is_not_ambiguous_unparseable(self):
        for version in ("4.2.0-M2", "4.1.0-RC1", "4.2.0-SNAPSHOT", "4.2.0-beta1"):
            with self.subTest(version=version):
                self.assertEqual("prerelease", _classify_version_change("4.0.6", version))

    def test_invalid_version_and_downgrade_are_distinct(self):
        self.assertEqual("unparseable", _classify_version_change("4.0.6", "${unknown}"))
        self.assertEqual("downgrade", _classify_version_change("4.0.6", "3.5.16"))

    def test_current_policy_still_rejects_prerelease(self):
        policy = SpringBootVersionPolicy(
            allow_patch=True, allow_minor=True, allow_major=False, allow_downgrade=False,
        )
        self.assertFalse(_spring_boot_change_allowed(
            {"detected_change_type": "prerelease", "final_version": "4.2.0-M2"}, policy
        ))

    def test_hook_preserves_historical_progress_without_prescribing_repair(self):
        hook = (ROOT / "scripts/openhands/openhands-gate2-stop-hook.sh").read_text()
        self.assertIn("Best earlier validated progress", hook)
        self.assertIn("Current validated progress", hook)
        self.assertIn("other failed constraints", hook)
        self.assertIn("validation-attempt-", hook)
        self.assertIn("choose and validate the next engineering action yourself", hook)

    def test_maven_skill_cautions_against_false_zero_finding_scans(self):
        skill = (ROOT / "scripts/openhands/skills/maven-dependency-evidence/SKILL.md").read_text()
        self.assertIn("incomplete/unknown", skill)
        self.assertIn("unresolved modules", skill)
        self.assertIn("group ID", skill)


if __name__ == "__main__":
    unittest.main()
