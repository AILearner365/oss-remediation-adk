"""Offline contracts for reusable Spring Boot release selection."""

from __future__ import annotations

import unittest

from spring_boot_release_intelligence.release_selection import (
    Metadata,
    ReleaseSelectionError,
    select_candidates,
    validate_resolved_selection,
)


VERSIONS = (
    "3.5.9", "4.0.6", "4.0.7", "4.0.8", "4.0.9-M1",
    "4.1.0", "4.1.1", "5.0.0-RC1", "5.0.0", "5.0.1",
)


def metadata() -> Metadata:
    return Metadata(VERSIONS, "fixture:maven-metadata.xml", "fixture-sha256")


class ReleaseSelectionTests(unittest.TestCase):
    def select(self, **kwargs):
        return select_candidates("4.0.6", metadata_loader=metadata, **kwargs)

    def test_default_discovers_only_forward_stable_patches(self):
        releases, evidence = self.select()
        self.assertEqual(["4.0.7", "4.0.8"], releases)
        self.assertEqual("automatic", evidence["mode"])
        self.assertEqual("fixture-sha256", evidence["metadata"]["sha256"])
        self.assertNotIn("excluded", evidence)
        self.assertIn("not enumerated", evidence["exclusion_reporting"])

    def test_single_and_multiple_ranges_are_complete(self):
        releases, evidence = self.select(ranges="4.0.x")
        self.assertEqual(["4.0.7", "4.0.8"], releases)
        self.assertNotIn("4.0.9-M1", releases)
        self.assertEqual(2, evidence["candidate_count"])
        releases, _ = self.select(ranges="4.0.x,4.1.x")
        self.assertEqual(["4.0.7", "4.0.8", "4.1.0", "4.1.1"], releases)

    def test_cross_major_range_is_supported_when_explicit(self):
        releases, _ = self.select(ranges="4.1.x,5.0.x")
        self.assertEqual(["4.1.0", "4.1.1", "5.0.0", "5.0.1"], releases)

    def test_explicit_versions_are_validated_and_deduplicated(self):
        releases, evidence = self.select(versions=" 4.1.1, 4.0.8 ,4.1.1 ")
        self.assertEqual(["4.0.8", "4.1.1"], releases)
        self.assertEqual(["4.1.1", "4.0.8"], evidence["requested"])

    def test_empty_csv_entries_are_rejected(self):
        for key, value in (("versions", "4.0.8,,4.1.1"),
                           ("ranges", "4.0.x,"),
                           ("versions", ["4.0.8", " "])):
            with self.subTest(key=key, value=value), self.assertRaisesRegex(
                    ReleaseSelectionError, "empty entry"):
                self.select(**{key: value})
        with self.assertRaisesRegex(ReleaseSelectionError, "empty entry"):
            self.select(config={"release_selection": {"ranges": ["4.0.x", ""]}})

    def test_invalid_unpublished_prerelease_and_downgrade_are_rejected(self):
        for versions, text in (("4.1", "invalid version"),
                               ("4.1.9", "not present"),
                               ("4.0.9-M1", "invalid version"),
                               ("3.5.9", "not newer")):
            with self.subTest(versions=versions), self.assertRaisesRegex(ReleaseSelectionError, text):
                self.select(versions=versions)

    def test_range_limit_is_rejected_without_truncation(self):
        with self.assertRaisesRegex(ReleaseSelectionError, "matched 4 candidates.*max_candidates=3"):
            self.select(ranges="4.0.x,4.1.x", max_candidates=3)

    def test_cli_and_config_selection_conflicts_are_rejected(self):
        with self.assertRaisesRegex(ReleaseSelectionError, "cannot be combined"):
            self.select(versions="4.0.8",
                        config={"release_selection": {"ranges": ["4.1.x"]}})

    def test_configuration_controls_selection_and_preserves_limit(self):
        releases, evidence = self.select(config={"release_selection": {
            "versions": ["4.0.8", "4.1.1"], "max_candidates": 2,
        }, "scanner": "fixture-scanner"})
        self.assertEqual(["4.0.8", "4.1.1"], releases)
        self.assertEqual("config", evidence["source"])
        self.assertEqual(2, evidence["max_candidates"])

    def test_legacy_bounded_range_remains_supported(self):
        releases, _ = self.select(ranges="4.0.7..4.1.0")
        self.assertEqual(["4.0.7", "4.0.8", "4.1.0"], releases)

    def test_resolved_selection_is_validated_without_metadata_lookup(self):
        candidates, selection = self.select(versions="4.0.8,4.1.1")
        self.assertEqual((candidates, selection), validate_resolved_selection(selection, "4.0.6"))
        with self.assertRaisesRegex(ReleaseSelectionError, "does not match"):
            validate_resolved_selection(selection, "4.0.7")


if __name__ == "__main__":
    unittest.main()
