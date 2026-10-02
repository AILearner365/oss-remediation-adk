from __future__ import annotations

import difflib
import json
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from autonomous_oss_remediation_agent.deterministic.validation import DeterministicValidator
from autonomous_oss_remediation_agent.models import CommandResult
from autonomous_oss_remediation_agent.workspace import RunWorkspace, TraceStore


def text_diff(name, before, after, context=3):
    return f"diff --git a/{name} b/{name}\n" + "".join(difflib.unified_diff(
        before, after, fromfile=f"a/{name}", tofile=f"b/{name}", n=context))


class OutcomeChangeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = RunWorkspace.create(self.temp.name, "run")
        self.workspace.repository.mkdir()
        self.trace = TraceStore(self.workspace)
        self.validator = DeterministicValidator(None, self.workspace, Mock(), None, None, self.trace)

    def evidence(self, diff, files=("settings.conf",), captured=True):
        with (patch.object(self.validator, "_capture_changed_files", return_value=(files, captured)),
              patch.object(self.validator, "_capture_diff_text", return_value=(diff, captured))):
            response = self.validator.outcome_change_evidence(1, "baseline")
        retained = json.loads(self.trace.resolve_evidence_reference(response["snapshotReference"]).read_text())
        full = self.trace.resolve_evidence_reference(response["diffReference"]).read_text(encoding="utf-8")
        self.assertEqual(diff, full)
        self.assertEqual(diff, retained["diff"])
        self.assertEqual(response["diffReference"], retained["diffReference"])
        return response, retained

    def test_short_complete_diff_excludes_file_headers(self):
        response, retained = self.evidence(text_diff("settings.conf", ["old\n", "same\n"], ["new\n", "same\n"]))
        self.assertEqual(response["lineChanges"], retained["lineChanges"])
        change = response["lineChanges"][0]
        self.assertEqual((1, 1), (change["addedCount"], change["removedCount"]))
        self.assertEqual(["new"], change["addedExcerpts"])
        self.assertEqual(["old"], change["removedExcerpts"])
        for level in (response, retained):
            self.assertTrue(level["lineChangeParsingComplete"])
            self.assertTrue(level["lineChangesComplete"])
            self.assertTrue(level["changedFilesComplete"])
            self.assertTrue(level["diffComplete"])
            self.assertTrue(level["lineChanges"][0]["addedExcerptsComplete"])
            self.assertTrue(level["lineChanges"][0]["removedExcerptsComplete"])

    def test_character_clipping_is_incomplete_at_both_levels_and_full_diff_remains(self):
        before = "x" * 7000 + "IMPORTANT_OLD_TAIL\n"
        after = "y" * 7000 + "IMPORTANT_NEW_TAIL\n"
        response, retained = self.evidence(text_diff("settings.conf", [before], [after]))
        self.assertFalse(response["diffComplete"])
        self.assertEqual(12000, len(response["diff"]))
        self.assertTrue(retained["diffComplete"])
        self.assertIn("IMPORTANT_NEW_TAIL", retained["diff"])
        self.assertIn("IMPORTANT_OLD_TAIL", retained["diff"])
        for level in (response, retained):
            change = level["lineChanges"][0]
            self.assertTrue(change["countsComplete"])
            for kind in ("added", "removed"):
                self.assertEqual(1, change[kind + "Count"])
                self.assertEqual(160, len(change[kind + "Excerpts"][0]))
                self.assertFalse(change[kind + "ExcerptsComplete"])
                self.assertEqual(1, change[kind + "ExcerptsClippedLines"])
            self.assertIn("diffReference", level["summaryRecovery"])

    def test_header_like_hunk_content_is_counted(self):
        response, _ = self.evidence(text_diff("settings.conf",
            ["--option\n", "--- apparent header\n"], ["++example\n", "+++ apparent header\n"]))
        change = response["lineChanges"][0]
        self.assertEqual((2, 2), (change["addedCount"], change["removedCount"]))
        self.assertEqual(["--option", "--- apparent header"], change["removedExcerpts"])
        self.assertEqual(["++example", "+++ apparent header"], change["addedExcerpts"])
        self.assertTrue(change["removedExcerptsComplete"])

    def test_real_git_diff_preserves_header_like_and_long_content(self):
        before, after = self.workspace.repository / "before.txt", self.workspace.repository / "after.txt"
        before.write_text("--old\n" + "a" * 160 + "removed-tail\n", encoding="utf-8")
        after.write_text("++new\n" + "b" * 160 + "added-tail\n", encoding="utf-8")
        result = subprocess.run(["git", "diff", "--no-index", "--", str(before), str(after)],
                                capture_output=True, check=False)
        self.assertEqual(1, result.returncode, result.stderr.decode())
        response, retained = self.evidence(result.stdout.decode("utf-8"))
        for level in (response, retained):
            change = level["lineChanges"][0]
            self.assertEqual((2, 2), (change["addedCount"], change["removedCount"]))
            self.assertEqual("++new", change["addedExcerpts"][0])
            self.assertEqual("--old", change["removedExcerpts"][0])
            self.assertFalse(change["addedExcerptsComplete"])
            self.assertFalse(change["removedExcerptsComplete"])

    def test_multiple_files_and_hunks(self):
        before = [f"line{number}\n" for number in range(20)]
        after = before.copy()
        after[1], after[18] = "changed1\n", "changed18\n"
        diff = text_diff("first.conf", before, after, context=1)
        self.assertEqual(2, diff.count("@@ -"))
        diff += text_diff("second.conf", [], ["new\n"])
        response, retained = self.evidence(diff, ("first.conf", "second.conf"))
        self.assertEqual(response["lineChanges"], retained["lineChanges"])
        self.assertEqual([("first.conf", 2, 2), ("second.conf", 1, 0)],
                         [(x["file"], x["addedCount"], x["removedCount"]) for x in response["lineChanges"]])

    def test_line_limits_are_independent_at_each_summary_level(self):
        for added, removed in ((6, 12), (7, 13), (12, 20), (13, 21)):
            with self.subTest(added=added, removed=removed):
                diff = text_diff("settings.conf", [f"old{i}\n" for i in range(removed)],
                                 [f"new{i}\n" for i in range(added)])
                response, retained = self.evidence(diff)
                for level, add_limit, remove_limit in ((response, 6, 12), (retained, 12, 20)):
                    change = level["lineChanges"][0]
                    self.assertEqual((added, removed), (change["addedCount"], change["removedCount"]))
                    self.assertEqual(min(added, add_limit), len(change["addedExcerpts"]))
                    self.assertEqual(min(removed, remove_limit), len(change["removedExcerpts"]))
                    self.assertEqual(added <= add_limit, change["addedExcerptsComplete"])
                    self.assertEqual(removed <= remove_limit, change["removedExcerptsComplete"])

    def test_file_limits_do_not_change_per_file_completeness(self):
        for count in (8, 9, 41):
            with self.subTest(count=count):
                files = tuple(f"file{i}.conf" for i in range(count))
                diff = "".join(text_diff(name, ["old\n"], ["new\n"]) for name in files)
                response, retained = self.evidence(diff, files)
                self.assertEqual(min(8, count), len(response["lineChanges"]))
                self.assertEqual(count <= 8, response["lineChangesComplete"])
                self.assertEqual(count <= 40, response["changedFilesComplete"])
                self.assertEqual(count, len(retained["lineChanges"]))
                self.assertTrue(retained["lineChangesComplete"])
                self.assertTrue(retained["changedFilesComplete"])
                self.assertTrue(all(x["addedExcerptsComplete"] for x in response["lineChanges"]))

    def test_unsupported_and_malformed_forms_never_claim_complete_counts(self):
        header = "diff --git a/settings.conf b/settings.conf\n--- a/settings.conf\n+++ b/settings.conf\n"
        cases = [
            "diff --git a/settings.conf b/settings.conf\nGIT binary patch\nliteral 3\nabc\n",
            "diff --cc settings.conf\n@@@ -1,1 -1,1 +1,1 @@@\n++new\n",
            header + "@@ -1,2 +1,1 @@\n-old\n+new\n",
            header + "@@ -1,1 +1,1 @@\n-old\n+new\n+extra\n",
            header + "-no-hunk-header\n+new\n",
            "unrecognized diff format\n",
        ]
        for diff in cases:
            with self.subTest(diff=diff):
                response, retained = self.evidence(diff)
                for level in (response, retained):
                    self.assertFalse(level["lineChangeParsingComplete"])
                    change = level["lineChanges"][0]
                    self.assertIn(change["summaryStatus"], {"unsupported", "unparseable"})
                    self.assertTrue(change["summaryError"])
                    self.assertIsNone(change["addedCount"])
                    self.assertIsNone(change["removedCount"])
                    self.assertFalse(change["addedExcerptsComplete"])
                    self.assertFalse(change["removedExcerptsComplete"])

    def test_empty_mode_only_and_no_newline_diffs(self):
        response, _ = self.evidence("", ())
        self.assertTrue(response["lineChangeParsingComplete"])
        self.assertEqual([], response["lineChanges"])
        response, _ = self.evidence("diff --git a/settings.conf b/settings.conf\nold mode 100644\nnew mode 100755\n")
        self.assertEqual(0, response["lineChanges"][0]["addedCount"])
        diff = ("diff --git a/settings.conf b/settings.conf\n--- a/settings.conf\n+++ b/settings.conf\n"
                "@@ -1 +1 @@\n-old\n\\ No newline at end of file\n+new\n\\ No newline at end of file\n")
        response, _ = self.evidence(diff)
        self.assertTrue(response["lineChangeParsingComplete"])
        self.assertEqual(1, response["lineChanges"][0]["removedCount"])

    def test_capture_failure_is_distinct_from_excerpt_and_file_list_bounds(self):
        response, retained = self.evidence("", (), captured=False)
        for level in (response, retained):
            self.assertFalse(level["captureSucceeded"])
            self.assertFalse(level["changedFilesComplete"])
            self.assertFalse(level["diffComplete"])
            self.assertFalse(level["lineChangeParsingComplete"])

    def test_untracked_diff_producer_emits_supported_text_hunks_and_explicit_binary(self):
        for data, count in ((b"++first\n--second", 2), (b"", 0), (b"\xff", None)):
            with self.subTest(data=data):
                (self.workspace.repository / "settings.conf").write_bytes(data)
                def command(argv, **kwargs):
                    return CommandResult(argv, str(self.workspace.repository), 0 if argv[1] == "diff" else 1)
                self.validator.process_runner.run_argv.side_effect = command
                with patch.object(self.validator, "_capture_changed_files", return_value=(("settings.conf",), True)):
                    response = self.validator.outcome_change_evidence(1, "baseline")
                change = response["lineChanges"][0]
                self.assertEqual(count, change["addedCount"])
                self.assertEqual(count is not None, change["addedExcerptsComplete"])
                self.assertTrue(self.trace.resolve_evidence_reference(response["diffReference"]).is_file())


if __name__ == "__main__":
    unittest.main()
