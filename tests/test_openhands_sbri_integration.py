"""Offline integration tests for pre-edit SBRI evidence; no model or network calls."""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.openhands.sbri_integration import (
    agent_message,
    applicability,
    require_valid_selection,
    retain_review_bundle,
    run_pre_edit_intelligence,
)


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/openhands/openhands-gate2-stop-hook-run.py"
FRESH_RUN = ROOT / "scripts/openhands/openhands-gate2-fresh-run.sh"
EXECUTE = ROOT / "scripts/openhands/openhands-gate2-execute.sh"


def counts(original=2, addressed=0, remaining=2, new=0, total=2):
    def value(number):
        return {"CRITICAL": number, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0}
    return {"original": value(original), "addressed": value(addressed),
            "remaining": value(remaining), "new": value(new), "total": value(total)}


def result(status="SUCCESS"):
    base = {"release": "4.0.6", "coordinate": "example:library", "selected_version": "1",
            "ownership": "BOOT_MANAGED", "override_source": None, "paths": [], "findings": []}
    candidate = {**base, "release": "4.0.8", "selected_version": "2"}
    return {
        "status": status,
        "application": {"original_spring_boot_version": "4.0.6"},
        "execution": {"evaluated_releases": ["4.0.6", "4.0.8"]},
        "releases": [
            {"version": "4.0.6", "assessment_status": "COMPLETE", "rank": None,
             "counts": counts()},
            {"version": "4.0.8", "assessment_status": "COMPLETE", "rank": 1,
             "counts": counts(addressed=1, remaining=1, total=1)},
        ],
        "dependencies": [base, candidate],
        "findings": [{"release": "4.0.8", "package": "example:library",
                      "advisory_id": "OSV-1", "severity": "CRITICAL",
                      "fixed_versions": ["3"], "evidence_reference": "evidence/scanner.json"}],
        "errors": ([] if status == "SUCCESS" else
                   [{"release": "4.0.7", "stage": "scanner", "message": "unavailable"}]),
    }


class SbriOpenHandsIntegrationTests(unittest.TestCase):
    def make_project(self, root: Path, *, boot=True) -> Path:
        project = root / "project"; project.mkdir()
        parent = ("<parent><groupId>org.springframework.boot</groupId>"
                  "<artifactId>spring-boot-starter-parent</artifactId><version>4.0.6</version></parent>"
                  if boot else "")
        (project / "pom.xml").write_text(
            f'<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion>{parent}'
            '<groupId>example</groupId><artifactId>app</artifactId><version>1</version></project>')
        subprocess.run(["git", "init", "-b", "task"], cwd=project, check=True, capture_output=True)
        subprocess.run(["git", "add", "pom.xml"], cwd=project, check=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.test",
                        "commit", "-m", "baseline"], cwd=project, check=True, capture_output=True)
        return project

    def execute(self, project: Path, state: Path, *, status="SUCCESS", exit_code=0,
                release_versions=None, release_ranges=None, config=None):
        invocations = []
        def fake_execute(command, **kwargs):
            invocations.append(command)
            output = Path(command[command.index("--output") + 1]); output.mkdir(parents=True)
            if exit_code in (0, 3) or status == "FAILURE":
                observed = result(status)
                manifest = Path(command[command.index("--resolved-selection-file") + 1])
                observed["execution"]["release_selection"] = json.loads(manifest.read_text())
                observed["execution"]["evaluated_releases"] = ["4.0.6", *candidates]
                (output / "result.json").write_text(json.dumps(observed))
                (output / "report.html").write_text("<html></html>")
                (output / "evidence").mkdir()
            kwargs["log"].write_text("fixture execution\n")
            return {"exitCode": exit_code, "wallSeconds": 1.0,
                    "peakProcessTreeRssKib": 100, "timedOut": False}
        candidates = list(dict.fromkeys((release_versions or "4.0.8").split(",")))
        mode = "explicit" if release_versions else ("range" if release_ranges else "automatic")
        selection = {"mode": mode, "source": "cli" if release_versions or release_ranges else "automatic",
                     "baseline": "4.0.6",
                     "requested": release_versions or release_ranges or ["4.0.x"],
                     "resolved_candidates": candidates, "candidate_count": len(candidates),
                     "max_candidates": 12,
                     "metadata": {"source": "fixture", "sha256": "x"}}
        with patch("scripts.openhands.sbri_integration.select_candidates",
                   return_value=(candidates, selection)), \
             patch("scripts.openhands.sbri_integration._execute_sbri", side_effect=fake_execute):
            record = run_pre_edit_intelligence(
                control_repo=ROOT, project=project,
                task="Resolve Maven Spring Boot security vulnerabilities", state_dir=state,
                release_versions=release_versions, release_ranges=release_ranges, config=config)
        return record, invocations

    def test_applicable_spring_boot_task_runs_before_edit_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); project = self.make_project(root)
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project, check=True,
                                  text=True, capture_output=True).stdout.strip()
            record, calls = self.execute(project, root / "state")
            self.assertEqual("COMPLETE", record["status"]); self.assertEqual(1, len(calls))
            self.assertTrue(record["deliveredBeforeAgentRun"]); self.assertTrue(record["sourceUnchanged"])
            self.assertEqual(head, subprocess.run(["git", "rev-parse", "HEAD"], cwd=project,
                             check=True, text=True, capture_output=True).stdout.strip())
            self.assertEqual("", subprocess.run(["git", "status", "--porcelain"], cwd=project,
                             check=True, text=True, capture_output=True).stdout)

    def test_unrelated_and_non_spring_tasks_do_not_invoke_sbri(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); spring = self.make_project(root)
            unrelated = run_pre_edit_intelligence(control_repo=ROOT, project=spring,
                task="Correct a README typo", state_dir=root / "state-unrelated")
            self.assertEqual("NOT_APPLICABLE", unrelated["status"]); self.assertFalse(unrelated["invoked"])
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); plain = self.make_project(root, boot=False)
            non_spring = run_pre_edit_intelligence(control_repo=ROOT, project=plain,
                task="Resolve Maven security vulnerabilities", state_dir=root / "state-plain")
            self.assertEqual("NOT_APPLICABLE", non_spring["status"]); self.assertFalse(non_spring["invoked"])

    def test_complete_summary_is_bounded_accurate_and_not_a_forced_strategy(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); project = self.make_project(root)
            record, _ = self.execute(project, root / "state")
            message = agent_message(record)
            self.assertLess(record["agentContextCharacters"], 6000)
            self.assertIn("baseline Spring Boot: 4.0.6", message)
            self.assertIn("addressed=1", message); self.assertIn("remaining Critical+High=1", message)
            self.assertIn("not necessarily the complete set of credible remediation candidates", message)
            self.assertIn("mandatory upgrade", message)
            self.assertFalse(record["rankForcedAsStrategy"])

    def test_partial_result_and_machine_readable_errors_are_preserved(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); project = self.make_project(root)
            record, _ = self.execute(project, root / "state", status="PARTIAL", exit_code=3)
            summary = json.loads(Path(record["summaryJsonPath"]).read_text())
            self.assertEqual("PARTIAL", record["status"]); self.assertTrue(record["deliveredBeforeAgentRun"])
            self.assertEqual("scanner", summary["errors"][0]["stage"])

    def test_baseline_failure_is_not_zero_findings_or_upgrade_impossibility(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); project = self.make_project(root)
            record, _ = self.execute(project, root / "state", status="FAILURE", exit_code=2)
            self.assertEqual("FAILED", record["status"]); self.assertFalse(record["deliveredBeforeAgentRun"])
            message = agent_message(record)
            self.assertIn("not evidence that Spring Boot upgrades are impossible", message)
            self.assertNotIn("zero vulnerabilities", message)

    def test_identical_request_reuses_retained_evidence_after_recovery(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); project = self.make_project(root); state = root / "state"
            first, calls = self.execute(project, state)
            second, second_calls = self.execute(project, state)
            self.assertEqual(1, len(calls)); self.assertEqual([], second_calls)
            self.assertTrue(second["reused"]); self.assertTrue(second["duplicateExecutionAvoided"])
            self.assertTrue(Path(second["resultPath"]).is_file())
            self.assertTrue((state / "sbri/latest.json").is_file())
            self.assertEqual(first["fingerprint"], second["fingerprint"])
            review = root / "review"
            retain_review_bundle(state / "sbri/latest.json", review)
            self.assertTrue((review / "output/result.json").is_file())
            self.assertTrue((review / "agent-summary.txt").is_file())

    def test_changed_candidate_scope_invalidates_cache_and_is_propagated(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); project = self.make_project(root); state = root / "state"
            first, first_calls = self.execute(project, state, release_versions="4.0.8")
            second, second_calls = self.execute(project, state, release_versions="4.0.8,4.1.1")
            self.assertEqual(1, len(first_calls)); self.assertEqual(1, len(second_calls))
            self.assertNotEqual(first["fingerprint"], second["fingerprint"])
            self.assertIn("--resolved-selection-file", second_calls[0])
            manifest = json.loads(Path(second["releaseSelectionPath"]).read_text())
            self.assertEqual(["4.0.8", "4.1.1"], manifest["resolved_candidates"])
            self.assertEqual(manifest, second["releaseSelection"])

    def test_changed_application_source_invalidates_cache(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); project = self.make_project(root); state = root / "state"
            source = project / "README.md"; source.write_text("before\n")
            subprocess.run(["git", "add", "README.md"], cwd=project, check=True)
            subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.test",
                            "commit", "-m", "source"], cwd=project, check=True, capture_output=True)
            first, _ = self.execute(project, state)
            source.write_text("after\n")
            second, calls = self.execute(project, state)
            self.assertEqual(1, len(calls))
            self.assertNotEqual(first["fingerprint"], second["fingerprint"])

    def test_config_is_hashed_and_forwarded_without_overriding_its_selection(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); project = self.make_project(root); state = root / "state"
            config = root / "sbri.json"
            config.write_text(json.dumps({"release_selection": {"versions": ["4.0.8"]},
                                          "scanner": "configured-scanner"}))
            record, calls = self.execute(project, state, config=config)
            self.assertIn("--config", calls[0]); self.assertIn("--resolved-selection-file", calls[0])
            self.assertNotIn("--releases", calls[0])
            self.assertNotIn("--scanner", calls[0])
            self.assertEqual("configured-scanner", record["request"]["config"]["content"]["scanner"])
            self.assertEqual("configured-scanner", record["request"]["scanner"]["requested"])

    def test_runner_places_sbri_before_agent_run_and_leaves_validator_authoritative(self):
        source = RUNNER.read_text()
        self.assertLess(source.index("run_pre_edit_intelligence("), source.index("conversation.send_message(task)"))
        self.assertIn('launcher_dir / "sbri"', source)
        self.assertIn("hook_config=hook_config", source)
        self.assertIn("DETERMINISTIC_VALIDATION_PASSED", source)
        self.assertIn('parser.add_argument("--sbri"', source)
        self.assertIn('selection.add_argument("--sbri-versions"', source)
        self.assertIn('selection.add_argument("--sbri-range"', source)
        self.assertIn("require_valid_selection(sbri_record)", source)
        self.assertLess(source.index("require_valid_selection(sbri_record)"),
                        source.index("conversation.send_message(task)"))
        self.assertIn("argparse.BooleanOptionalAction", source)

    def test_invalid_selection_stops_before_model_boundary(self):
        for message in ("malformed version", "conflicting selection", "candidate limit exceeded"):
            with self.subTest(message=message), self.assertRaisesRegex(SystemExit, message):
                require_valid_selection({"status": "INVALID_RELEASE_SELECTION", "message": message})
        require_valid_selection({"status": "FAILED", "message": "scanner unavailable"})

    def test_candidate_resolution_occurs_once_and_manifest_is_evaluated(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); project = self.make_project(root); state = root / "state"
            first = {"baseline": "4.0.6", "mode": "range", "source": "cli",
                     "requested": ["4.0.x"], "resolved_candidates": ["4.0.7"],
                     "candidate_count": 1, "max_candidates": 12,
                     "metadata": {"source": "fixture", "sha256": "first"}}
            calls = []
            def execute(command, **kwargs):
                manifest = json.loads(Path(command[command.index("--resolved-selection-file") + 1]).read_text())
                calls.append(manifest)
                output = Path(command[command.index("--output") + 1]); output.mkdir(parents=True)
                observed = result(); observed["execution"]["release_selection"] = manifest
                observed["execution"]["evaluated_releases"] = ["4.0.6", *manifest["resolved_candidates"]]
                (output / "result.json").write_text(json.dumps(observed)); (output / "report.html").write_text("x")
                return {"exitCode": 0, "wallSeconds": 1, "peakProcessTreeRssKib": 1, "timedOut": False}
            with patch("scripts.openhands.sbri_integration.select_candidates",
                       return_value=(["4.0.7"], first)) as selector, \
                 patch("scripts.openhands.sbri_integration._execute_sbri", side_effect=execute):
                record = run_pre_edit_intelligence(control_repo=ROOT, project=project,
                    task="Resolve Maven Spring Boot security vulnerabilities", state_dir=state,
                    release_ranges="4.0.x")
            selector.assert_called_once()
            self.assertEqual([first], calls)
            output = json.loads(Path(record["resultPath"]).read_text())
            self.assertEqual(first, output["execution"]["release_selection"])
            self.assertEqual(first, record["releaseSelection"])

    def test_gate2_shell_launchers_forward_release_selection_arguments(self):
        fresh = FRESH_RUN.read_text(); execute = EXECUTE.read_text()
        self.assertIn('SBRI_ARGS=("$@")', fresh)
        self.assertIn('"${SBRI_ARGS[@]}"', fresh)
        self.assertIn('SBRI_ARGS=("$@")', execute)
        self.assertIn('"${SBRI_ARGS[@]}"', execute)


if __name__ == "__main__":
    unittest.main()
