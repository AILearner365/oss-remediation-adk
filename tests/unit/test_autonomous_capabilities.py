from __future__ import annotations
from tests.checkpoint_fixtures import typed_intent_answers

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import PropertyMock, patch

from google.adk.models import Gemini

from autonomous_oss_remediation_agent.agent import create_remediation_agent
from autonomous_oss_remediation_agent.capabilities import DeveloperCapabilitySet, ExecutionBudget, ProcessRunner, WorkspaceIO
from autonomous_oss_remediation_agent.capabilities import isolation as isolation_module
from autonomous_oss_remediation_agent.capabilities.research import (
    HttpResearchProvider,
    ResearchResult,
    ResearchStatus,
)
from autonomous_oss_remediation_agent.capabilities.policy import evaluate_runtime_boundary
from autonomous_oss_remediation_agent.config import ExecutionBudgetConfig, RuntimePolicy
from autonomous_oss_remediation_agent.journal import JournalLifecycle, JournalStore
from autonomous_oss_remediation_agent.workspace import RunWorkspace, TraceStore, WorkspaceBoundaryError


class AutonomousCapabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = RunWorkspace.create(self.temp.name, "run")
        self.workspace.repository.mkdir()
        self.trace = TraceStore(self.workspace)
        self.budget = ExecutionBudget(
            ExecutionBudgetConfig(
                max_cycles=2,
                max_tool_calls=20,
                command_timeout_seconds=15,
                overall_timeout_seconds=30,
                max_returned_output_chars=2000,
            )
        )
        policy = RuntimePolicy(
            trusted_repository=True,
            dedicated_runner=True,
            enable_autonomous_shell=True,
        )
        self.runner = ProcessRunner(self.workspace, self.trace, self.budget, policy)
        self.io = WorkspaceIO(self.workspace, self.trace)
        self.capabilities = DeveloperCapabilitySet(self.io, self.runner, self.budget, self.trace)

    def tearDown(self):
        self.temp.cleanup()

    def test_runtime_boundary_is_fail_closed(self):
        self.assertFalse(evaluate_runtime_boundary(RuntimePolicy()).approved)
        self.assertFalse(
            evaluate_runtime_boundary(RuntimePolicy(trusted_repository=True, dedicated_runner=True)).approved
        )
        approved = evaluate_runtime_boundary(
            RuntimePolicy(trusted_repository=True, dedicated_runner=True, enable_autonomous_shell=True)
        )
        self.assertTrue(approved.approved)
        self.assertIn("no hard shell containment", approved.reason)

    def test_linux_isolation_backend_selection_fails_closed(self):
        with (
            patch.object(isolation_module.sys, "platform", "linux"),
            patch.object(isolation_module, "_linux_landlock_abi", return_value=0),
            patch.object(isolation_module, "_linux_mount_namespace_usable", return_value=False),
        ):
            self.assertIsNone(isolation_module._linux_isolation_backend())
        with (
            patch.object(isolation_module.sys, "platform", "linux"),
            patch.object(isolation_module, "_linux_landlock_abi", return_value=0),
            patch.object(isolation_module, "_linux_mount_namespace_usable", return_value=True),
        ):
            self.assertEqual(
                "linux-user-mount-namespace", isolation_module._linux_isolation_backend()
            )
        with (
            patch.object(isolation_module.sys, "platform", "linux"),
            patch.object(isolation_module, "_linux_landlock_abi", return_value=6),
            patch.object(isolation_module, "_linux_mount_namespace_usable", return_value=True),
        ):
            self.assertEqual("linux-landlock", isolation_module._linux_isolation_backend())

    def test_nested_namespace_probe_result_classification_is_fail_closed(self):
        for returncode in (10, 11, 12, 20):
            with self.subTest(returncode=returncode):
                self.assertTrue(isolation_module._nested_namespace_escape_denied(returncode))
        for returncode in (0, 1, 2, 13, 19, 21, 126, 127, -9):
            with self.subTest(returncode=returncode):
                self.assertFalse(isolation_module._nested_namespace_escape_denied(returncode))

    def test_read_edit_and_path_boundary(self):
        result = self.capabilities.edit_workspace_text("write", "pom.xml", content="<project/>\n")
        self.assertEqual("ok", result["status"])
        read = self.capabilities.read_workspace_text("pom.xml")
        self.assertEqual("<project/>", read["content"])
        replaced = self.capabilities.edit_workspace_text(
            "replace",
            "pom.xml",
            old_text="project",
            new_text="model",
            expected_occurrences=1,
        )
        self.assertNotEqual(replaced["beforeSha256"], replaced["afterSha256"])
        removed_text = self.capabilities.edit_workspace_text(
            "replace", "pom.xml", old_text="model", new_text="",
        )
        self.assertEqual("ok", removed_text["status"])
        self.assertEqual("</>\n", (self.workspace.repository / "pom.xml").read_text(encoding="utf-8"))
        mistaken_delete = self.capabilities.edit_workspace_text("delete", "pom.xml")
        self.assertEqual("error", mistaken_delete["status"])
        self.assertTrue((self.workspace.repository / "pom.xml").is_file())
        deleted = self.capabilities.delete_workspace_file("pom.xml")
        self.assertEqual("delete_file", deleted["action"])
        self.assertFalse((self.workspace.repository / "pom.xml").exists())
        with self.assertRaises(WorkspaceBoundaryError):
            self.io.read_text("../outside.txt")
        with self.assertRaises(WorkspaceBoundaryError):
            self.io.read_text(str(Path(self.temp.name).resolve()))
        with self.assertRaises(WorkspaceBoundaryError):
            self.io.edit_text("write", ".git/config", content="bad")

    def test_read_and_search_continue_without_large_responses(self):
        (self.workspace.repository / "long.txt").write_text("X" * 12000 + "\nneedle\nneedle\n",
                                                          encoding="utf-8")
        first = self.capabilities.read_workspace_text("long.txt")
        self.assertEqual(8000, len(first["content"]))
        self.assertFalse(first["complete"])
        continuation = self.capabilities.read_workspace_text(
            "long.txt", start_line=first["nextStartLine"],
            start_column=first["nextStartColumn"])
        self.assertTrue(continuation["content"].startswith("X" * 4000))
        self.assertTrue(continuation["readCoverageComplete"])
        self.assertIsNotNone(continuation["readReceipt"])
        first_search = self.capabilities.search_workspace_text("needle", max_results=1)
        self.assertTrue(first_search["moreExists"])
        second_search = self.capabilities.search_workspace_text("needle", max_results=1,
                                                                cursor=first_search["nextCursor"])
        self.assertEqual(3, second_search["results"][0]["line"])
        invalid = self.capabilities.search_workspace_text("different", cursor=second_search["nextCursor"])
        self.assertEqual("TOOL_ERROR", invalid["failureCode"])

    def test_partial_read_cannot_reconstruct_existing_file_without_complete_current_receipt(self):
        config = self.workspace.repository / "settings.conf"
        content = "version=1\n" + "".join(f"option.{number}=unchanged\n" for number in range(500))
        content += "[unrelated-trailing-section]\nkeep=true\n"
        config.write_text(content, encoding="utf-8")
        first = self.capabilities.read_workspace_text("settings.conf")
        self.assertTrue(first["moreExists"])
        self.assertFalse(first["fileComplete"])
        self.assertFalse(first["readCoverageComplete"])
        self.assertIsNone(first["readReceipt"])
        self.assertIn("revision checksum", first["handleGuidance"])
        self.assertIn("nextStartLine/nextStartColumn", first["handleGuidance"])
        prefix_reconstruction = self.capabilities.edit_workspace_text(
            "replace", "settings.conf", old_text=first["content"],
            new_text=first["content"].replace("version=1", "version=2") + "\n[reconstructed-end]",
        )
        self.assertEqual("error", prefix_reconstruction["status"])
        self.assertIn("partial read excerpt", prefix_reconstruction["error"])
        no_receipt = self.capabilities.edit_workspace_text("write", "settings.conf", content="version=2\n")
        self.assertEqual("error", no_receipt["status"])
        self.assertIn("read_receipt", no_receipt["error"])
        checksum_as_receipt = self.capabilities.edit_workspace_text(
            "write", "settings.conf", content="version=2\n", read_receipt=first["fileSha256"])
        self.assertEqual("error", checksum_as_receipt["status"])
        self.assertIn("fileSha256 checksum", checksum_as_receipt["error"])
        retained_path = self.workspace.artifacts / "commands" / "handle-test.log"
        retained_path.parent.mkdir(parents=True, exist_ok=True)
        retained_path.write_text("retained", encoding="utf-8")
        issued_reference = self.trace.issue_evidence_reference(retained_path)
        reference_as_receipt = self.capabilities.edit_workspace_text(
            "write", "settings.conf", content="version=2\n",
            read_receipt=issued_reference.removeprefix("evidence:"))
        self.assertEqual("error", reference_as_receipt["status"])
        self.assertIn("evidence reference", reference_as_receipt["error"])
        targeted = self.capabilities.edit_workspace_text(
            "replace", "settings.conf", old_text="version=1", new_text="version=2")
        self.assertEqual("ok", targeted["status"])
        self.assertIn("[unrelated-trailing-section]", config.read_text(encoding="utf-8"))
        stale = self.capabilities.edit_workspace_text(
            "write", "settings.conf", content="version=3\n", read_receipt="invented")
        self.assertEqual("error", stale["status"])
        first = self.capabilities.read_workspace_text("settings.conf")
        last = self.capabilities.read_workspace_text("settings.conf", start_line=first["nextStartLine"])
        self.assertTrue(last["readCoverageComplete"])
        self.assertIsNotNone(last["readReceipt"])
        config.write_text(config.read_text(encoding="utf-8") + "external=true\n", encoding="utf-8")
        stale_after_external_edit = self.capabilities.edit_workspace_text(
            "write", "settings.conf", content="version=3\n", read_receipt=last["readReceipt"])
        self.assertEqual("error", stale_after_external_edit["status"])
        first = self.capabilities.read_workspace_text("settings.conf")
        last = self.capabilities.read_workspace_text("settings.conf", start_line=first["nextStartLine"])
        self.assertTrue(last["readCoverageComplete"])
        deliberate_rewrite = self.capabilities.edit_workspace_text(
            "write", "settings.conf", content="version=3\n", read_receipt=last["readReceipt"])
        self.assertEqual("ok", deliberate_rewrite["status"])
        self.assertEqual("version=3\n", config.read_text(encoding="utf-8"))
        repeated = self.capabilities.edit_workspace_text(
            "write", "settings.conf", content="version=4\n", read_receipt=last["readReceipt"])
        self.assertEqual("error", repeated["status"])

    def test_symlink_escape_is_rejected_when_supported(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        link = self.workspace.repository / "link"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except OSError:
            self.skipTest("Symlink creation is unavailable on this host")
        with self.assertRaises(WorkspaceBoundaryError):
            self.io.edit_text("write", "link/escape.txt", content="bad")

    def test_shell_returns_evidence_and_blocks_delivery(self):
        result = self.capabilities.run_workspace_shell("Write-Output capability-ok" if os.name == "nt" else "printf capability-ok")
        self.assertEqual(0, result["exitCode"])
        self.assertIn("capability-ok", result["stdout"])
        self.assertTrue(Path(result["stdoutArtifact"]).is_file())
        blocked = self.capabilities.run_workspace_shell("git push origin main")
        self.assertTrue(blocked["blocked"])
        self.assertEqual(126, blocked["exitCode"])

    def test_shell_retains_large_output_and_retrieves_bounded_evidence(self):
        command = "Write-Output ('A' * 12000)" if os.name == "nt" else "python -c \"print('A'*12000)\""
        result = self.capabilities.run_workspace_shell(command)
        self.assertFalse(result["stdoutComplete"])
        self.assertLess(len(result["stdout"]), 2200)
        self.assertGreater(Path(result["stdoutArtifact"]).stat().st_size, 12000)
        self.assertEqual(Path(result["stdoutArtifact"]).stat().st_size, result["stdoutBytes"])
        self.assertIn("query=", result["stdoutRecovery"])
        self.assertEqual(self.budget.config.max_tool_calls - self.budget.tool_calls,
                         result["remainingToolCalls"])
        reference = result["stdoutReference"]
        source = self.workspace.repository / "source.txt"
        source.write_text("repository content", encoding="utf-8")
        read = self.capabilities.read_workspace_text("source.txt")
        fabricated = self.capabilities.retrieve_retained_evidence("evidence:" + read["fileSha256"])
        self.assertEqual("TOOL_ERROR", fabricated["failureCode"])
        self.assertIn("fileSha256", fabricated["error"])
        self.assertIn("nextStartLine/nextStartColumn", fabricated["error"])
        receipt_as_reference = self.capabilities.retrieve_retained_evidence(read["readReceipt"])
        self.assertEqual("TOOL_ERROR", receipt_as_reference["failureCode"])
        self.assertIn("readReceipt", receipt_as_reference["error"])
        first = self.capabilities.retrieve_retained_evidence(reference, max_bytes=100)
        self.assertEqual("A" * 100, first["content"])
        self.assertFalse(first["complete"])
        second = self.capabilities.retrieve_retained_evidence(reference, start_offset=first["nextOffset"], max_bytes=100)
        self.assertEqual("A" * 100, second["content"])
        matches = self.capabilities.retrieve_retained_evidence(reference, query="AAAA", max_bytes=100)
        self.assertTrue(matches["matches"])
        self.assertEqual("TOOL_ERROR", self.capabilities.retrieve_retained_evidence("evidence:unknown")["failureCode"])
        self.assertIn("Unknown or expired", self.capabilities.retrieve_retained_evidence("evidence:unknown")["error"])
        outside = Path(self.temp.name) / "outside.txt"
        outside.write_text("secret", encoding="utf-8")
        with self.assertRaises(WorkspaceBoundaryError):
            self.trace.issue_evidence_reference(outside)
        Path(result["stdoutArtifact"]).write_text("changed", encoding="utf-8")
        self.assertIn("expired", self.capabilities.retrieve_retained_evidence(reference)["error"])

    def test_large_retained_log_supports_one_targeted_search_with_budget_metadata(self):
        raw = ("download progress\r" * 13_000 +
               "TREE FACT: generic dependency relationship\n" + "tail marker\n").encode("utf-8")
        path = self.workspace.artifacts / "commands" / "large-generic.stdout.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        reference = self.trace.issue_evidence_reference(path)
        before = self.budget.tool_calls
        found = self.capabilities.retrieve_retained_evidence(reference, query="TREE FACT")
        self.assertEqual(before + 1, self.budget.tool_calls)
        self.assertEqual(self.budget.config.max_tool_calls - self.budget.tool_calls,
                         found["remainingToolCalls"])
        self.assertEqual(self.budget.config.max_llm_calls_per_turn, found["modelTurnCallLimit"])
        self.assertEqual(len(raw), found["totalBytes"])
        self.assertEqual(1, len(found["matches"]))
        self.assertGreater(found["matches"][0]["offset"], 200_000)
        self.assertIn("generic dependency relationship", found["matches"][0]["text"])
        self.assertLess(len(found["matches"][0]["text"]), 400)
        first = self.capabilities.retrieve_retained_evidence(reference, max_bytes=4000)
        self.assertIn("query=", first["recovery"])
        self.assertEqual(len(raw), first["totalBytes"])
        tail = self.capabilities.retrieve_retained_evidence(reference, start_offset=len(raw) - 12)
        self.assertEqual(raw[-12:].decode(), tail["content"])

    def test_scanner_model_payload_is_compact_and_evidence_is_retrievable(self):
        from autonomous_oss_remediation_agent.models import ScanReport, VulnerabilityFinding

        class LargeScanner:
            backend = "fake"

            def scan(_, repository, severity_scope, label, *, runtime_resource=None):
                raw = self.workspace.artifacts / "scans" / f"{label}.json"
                raw.parent.mkdir(parents=True, exist_ok=True)
                raw.write_text("RAW-SCAN-" + "Z" * 20000, encoding="utf-8")
                finding = VulnerabilityFinding("CVE-TEST", (), "HIGH", "g", "a", "g:a", "1",
                                               summary="S" * 4000, backend_evidence={"raw": "Z" * 10000})
                return ScanReport(True, (finding,), None, str(raw), attempts=({"outcome": "COMPLETED_WITH_FINDINGS",
                                   "commandResult": {"stdout": "Z" * 20000}},), backend="fake")

        capabilities = DeveloperCapabilitySet(self.io, self.runner, self.budget, self.trace,
                                               scanner=LargeScanner())
        result = capabilities.scan_current_repository()
        self.assertEqual("COMPLETED_WITH_FINDINGS", result["outcome"])
        self.assertEqual(1, result["findingCount"])
        self.assertTrue(result["findingsComplete"])
        self.assertTrue(result["findingDetailsOmitted"])
        self.assertFalse(result["complete"])
        self.assertTrue(result["moreExists"])
        self.assertEqual("CVE-TEST", result["findings"][0]["vulnerabilityId"])
        self.assertNotIn("backendEvidence", result["findings"][0])
        self.assertLess(len(json.dumps(result)), 3000)
        self.assertEqual(1, result["attemptSummary"]["count"])
        raw = capabilities.retrieve_retained_evidence(result["rawEvidenceReference"], max_bytes=50)
        self.assertEqual("RAW-SCAN-", raw["content"][:9])
        self.assertFalse(raw["complete"])
        detail = capabilities.retrieve_retained_evidence(result["evidenceReference"], query="backendEvidence")
        self.assertTrue(detail["matches"])
        self.assertGreater(len((self.workspace.artifacts / "scans" / "engineering-cycle-0-authoritative-1.json").read_text()), 20000)

    def test_scan_completeness_for_small_and_over_limit_findings(self):
        from autonomous_oss_remediation_agent.models import ScanReport, VulnerabilityFinding

        class FindingsScanner:
            backend = "fake"

            def __init__(self, count):
                self.count = count

            def scan(scanner, repository, severity_scope, label, *, runtime_resource=None):
                raw = self.workspace.artifacts / "scans" / f"{label}.json"
                raw.parent.mkdir(parents=True, exist_ok=True)
                raw.write_text("{}", encoding="utf-8")
                findings = tuple(
                    VulnerabilityFinding(f"CVE-{index}", (), "HIGH", "g", f"a{index}",
                                         f"g:a{index}", "1", summary="brief")
                    for index in range(scanner.count)
                )
                report = ScanReport(True, findings, None, str(raw), backend="fake")
                self.trace.write_json(f"scans/{label}.normalized.json", report.to_dict())
                return report

        for count in (1, 27):
            with self.subTest(count=count):
                capabilities = DeveloperCapabilitySet(self.io, self.runner, self.budget, self.trace,
                                                       scanner=FindingsScanner(count))
                result = capabilities.scan_current_repository()
                self.assertEqual(count, result["findingCount"])
                self.assertEqual(min(count, 25), len(result["findings"]))
                self.assertEqual(count <= 25, result["findingsComplete"])
                self.assertFalse(result["findingDetailsOmitted"])
                self.assertEqual(count <= 25, result["complete"])
                self.assertEqual(count > 25, result["moreExists"])
                self.assertEqual("COMPLETED_WITH_FINDINGS", result["outcome"])
                self.assertIsNotNone(result["rawEvidenceReference"])
                if count > 25:
                    detail = capabilities.retrieve_retained_evidence(result["evidenceReference"],
                                                                      query="CVE-26")
                    self.assertTrue(detail["matches"])

    def test_evidence_references_are_isolated_between_runs(self):
        other_workspace = RunWorkspace.create(self.temp.name, "other-run")
        other_workspace.repository.mkdir()
        other_trace = TraceStore(other_workspace)
        same_relative = "commands/same.log"
        first = self.trace.write_text(same_relative, "same evidence")
        second = other_trace.write_text(same_relative, "same evidence")
        reference_a = self.trace.issue_evidence_reference(first)
        reference_b = other_trace.issue_evidence_reference(second)
        self.assertNotEqual(reference_a, reference_b)
        other_io = WorkspaceIO(other_workspace, other_trace)
        other_runner = ProcessRunner(other_workspace, other_trace, self.budget,
                                     self.runner.runtime_policy)
        other_capabilities = DeveloperCapabilitySet(other_io, other_runner, self.budget, other_trace)
        rejected = other_capabilities.retrieve_retained_evidence(reference_a)
        self.assertEqual("TOOL_ERROR", rejected["failureCode"])
        self.assertIn("Unknown or expired", rejected["error"])
        self.assertEqual("same evidence", other_capabilities.retrieve_retained_evidence(reference_b)["content"])

    def test_shell_supports_discovery_and_strips_credential_environment(self):
        (self.workspace.repository / "nested").mkdir()
        (self.workspace.repository / "nested" / "pom.xml").write_text("<project/>", encoding="utf-8")
        previous = os.environ.get("GH_TOKEN")
        previous_xray = os.environ.get("XRAY_ACCESS_TOKEN")
        os.environ["GH_TOKEN"] = "must-not-be-visible"
        os.environ["XRAY_ACCESS_TOKEN"] = "xray-must-not-be-visible"
        try:
            command = (
                "Get-ChildItem -Recurse -Filter pom.xml | Select-Object -ExpandProperty Name; "
                "Write-Output $env:GH_TOKEN; Write-Output $env:XRAY_ACCESS_TOKEN"
                if os.name == "nt"
                else "find . -name pom.xml -print; printf '%s%s' \"$GH_TOKEN\" \"$XRAY_ACCESS_TOKEN\""
            )
            result = self.capabilities.run_workspace_shell(command)
        finally:
            if previous is None:
                os.environ.pop("GH_TOKEN", None)
            else:
                os.environ["GH_TOKEN"] = previous
            if previous_xray is None:
                os.environ.pop("XRAY_ACCESS_TOKEN", None)
            else:
                os.environ["XRAY_ACCESS_TOKEN"] = previous_xray
        self.assertEqual(0, result["exitCode"])
        self.assertIn("pom.xml", result["stdout"])
        self.assertNotIn("must-not-be-visible", result["stdout"])
        self.assertNotIn("xray-must-not-be-visible", result["stdout"])

    def test_command_timeout_is_enforced(self):
        command = "Start-Sleep -Seconds 3" if os.name == "nt" else "sleep 3"
        result = self.runner.run_agent_shell(command, timeout_seconds=1)
        self.assertTrue(result.timed_out)
        self.assertEqual(124, result.exit_code)

    def test_deterministic_repository_process_strips_scanner_and_github_credentials(self):
        previous = os.environ.get("XRAY_ACCESS_TOKEN")
        previous_github = os.environ.get("GITHUB_TOKEN")
        os.environ["XRAY_ACCESS_TOKEN"] = "deterministic-secret"
        os.environ["GITHUB_TOKEN"] = "github-deterministic-secret"
        try:
            command = (
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    "Write-Output $env:XRAY_ACCESS_TOKEN; Write-Output $env:GITHUB_TOKEN",
                ]
                if os.name == "nt"
                else ["/bin/sh", "-c", "printf '%s%s' \"$XRAY_ACCESS_TOKEN\" \"$GITHUB_TOKEN\""]
            )
            result = self.runner.run_argv(command, cwd=self.workspace.repository)
        finally:
            if previous is None:
                os.environ.pop("XRAY_ACCESS_TOKEN", None)
            else:
                os.environ["XRAY_ACCESS_TOKEN"] = previous
            if previous_github is None:
                os.environ.pop("GITHUB_TOKEN", None)
            else:
                os.environ["GITHUB_TOKEN"] = previous_github
        self.assertTrue(result.succeeded)
        self.assertNotIn("deterministic-secret", result.stdout)
        self.assertNotIn("github-deterministic-secret", result.stdout)

    def test_budget_is_enforced_by_tool_bindings(self):
        budget = ExecutionBudget(
            ExecutionBudgetConfig(max_tool_calls=1, overall_timeout_seconds=30, command_timeout_seconds=5)
        )
        capabilities = DeveloperCapabilitySet(self.io, self.runner, budget, self.trace)
        capabilities.edit_workspace_text("write", "one.txt", content="1")
        exhausted = capabilities.read_workspace_text("one.txt")
        self.assertEqual("EXECUTION_BUDGET_EXCEEDED", exhausted["failureCode"])

    def test_adk_tool_surface_matches_capability_categories(self):
        tools = self.capabilities.adk_tools()
        self.assertEqual(
            {
                "read_workspace_text",
                "list_workspace_files",
                "search_workspace_text",
                "inspect_git_state",
                "edit_workspace_text",
                "delete_workspace_file",
                "run_workspace_shell",
                "scan_current_repository",
                "retrieve_retained_evidence",
                "research_search",
                "research_fetch",
                "submit_cycle_intent",
                "submit_cycle_outcome",
            },
            {tool.name for tool in tools},
        )
        declarations = {tool.name: tool._get_declaration() for tool in tools}
        for checkpoint_tool in ("submit_cycle_intent", "submit_cycle_outcome"):
            schema = declarations[checkpoint_tool].parameters_json_schema
            answer_ref = schema["properties"]["answers"]["items"]["$ref"].split("/")[-1]
            answer_schema = schema["$defs"][answer_ref]
            self.assertEqual({"section", "answer"}, set(answer_schema["required"]))
            expected = ({"section", "answer", "evidence", "candidates", "selection"}
                        if checkpoint_tool == "submit_cycle_intent" else {"section", "answer"})
            self.assertEqual(expected, set(answer_schema["properties"]))
        self.assertEqual(
            ["write", "replace"],
            declarations["edit_workspace_text"].parameters_json_schema["properties"]["action"]["enum"],
        )
        retrieval_schema = declarations["retrieve_retained_evidence"].parameters_json_schema
        self.assertTrue({"reference", "start_offset", "max_bytes", "query"}.issubset(
            retrieval_schema["properties"]))
        self.assertIn("prefer query", declarations["retrieve_retained_evidence"].description)
        self.assertIn("fileSha256", declarations["read_workspace_text"].description)
        self.assertIn("readReceipt", declarations["edit_workspace_text"].description)
        self.assertIn("do not construct", declarations["retrieve_retained_evidence"].description)
        self.assertIn("cursor", declarations["search_workspace_text"].parameters_json_schema["properties"])
        self.assertIn("start_column", declarations["read_workspace_text"].parameters_json_schema["properties"])

    def test_one_primary_adk_agent_uses_capability_surface(self):
        agent = create_remediation_agent(self.capabilities, "gemini-2.5-flash")
        self.assertEqual("autonomous_oss_remediation_agent", agent.name)
        self.assertIsInstance(agent.model, Gemini)
        self.assertEqual("gemini-2.5-flash", agent.model.model)
        self.assertEqual(7, agent.model.retry_options.attempts)
        self.assertEqual(2.0, agent.model.retry_options.initial_delay)
        self.assertEqual(30.0, agent.model.retry_options.max_delay)
        self.assertEqual(2.0, agent.model.retry_options.exp_base)
        self.assertEqual(1.0, agent.model.retry_options.jitter)
        self.assertIsNone(agent.model.retry_options.http_status_codes)
        import asyncio
        names = {tool.name for tool in asyncio.run(agent.tools[0].get_tools())}
        self.assertTrue({"read_workspace_text", "edit_workspace_text", "run_workspace_shell"}.issubset(names))

    def test_pre_intent_discovery_is_bounded_read_only_and_finds_late_files(self):
        for index in range(12):
            directory = self.workspace.repository / f"module-{index:02d}"
            directory.mkdir()
            (directory / "config.txt").write_text(
                "needle-value\n" if index == 11 else "ordinary\n",
                encoding="utf-8",
            )
        journal = JournalLifecycle(JournalStore(self.trace), self.trace, "contract", lambda: False)
        journal.begin_cycle(1)
        capabilities = DeveloperCapabilitySet(self.io, self.runner, self.budget, self.trace, journal)
        capabilities.begin_cycle(1)
        before = {
            path.relative_to(self.workspace.repository).as_posix(): path.read_bytes()
            for path in self.workspace.repository.rglob("*") if path.is_file()
        }

        first = capabilities.list_workspace_files(max_entries=5)
        second = capabilities.list_workspace_files(max_entries=5, cursor=first["nextCursor"])
        search = capabilities.search_workspace_text("needle-value", max_results=5)

        self.assertTrue(first["truncated"])
        self.assertNotEqual(first["files"], second["files"])
        self.assertEqual("module-11/config.txt", search["results"][0]["path"])
        after = {
            path.relative_to(self.workspace.repository).as_posix(): path.read_bytes()
            for path in self.workspace.repository.rglob("*") if path.is_file()
        }
        self.assertEqual(before, after)
        edited = capabilities.edit_workspace_text("write", "mutated.txt", content="isolated")
        self.assertEqual("ok", edited["status"])
        self.assertFalse((self.workspace.repository / "mutated.txt").exists())
        self.assertTrue(
            (self.workspace.investigation / "cycle-1" / "repository" / "mutated.txt").is_file()
        )

    def test_file_listing_bounds_traversal_and_continues_without_duplicates(self):
        for index in range(17):
            suffix = "txt" if index % 2 == 0 else "md"
            (self.workspace.repository / f"file-{index:02d}.{suffix}").write_text(
                str(index), encoding="utf-8"
            )
        before = {
            path.name: path.read_bytes()
            for path in self.workspace.repository.iterdir() if path.is_file()
        }

        pages = []
        cursor = None
        while True:
            page = self.io.list_files(
                max_entries=3,
                cursor=cursor,
                max_scanned_entries=4,
            )
            pages.append(page)
            self.assertLessEqual(page["scannedEntries"], 4)
            if page["nextCursor"] is None:
                break
            self.assertTrue(page["truncated"])
            self.assertIn(page["truncationReason"], {"PAGE_LIMIT", "SCAN_LIMIT"})
            self.assertIsNone(page["totalMatches"])
            self.assertFalse(page["totalMatchesExact"])
            cursor = page["nextCursor"]

        files = [path for page in pages for path in page["files"]]
        self.assertEqual(17, len(files))
        self.assertEqual(17, len(set(files)))
        self.assertFalse(pages[-1]["truncated"])
        self.assertIsNone(pages[-1]["truncationReason"])
        self.assertTrue(pages[-1]["totalMatchesExact"])
        self.assertEqual(17, pages[-1]["totalMatches"])

        txt_files = []
        cursor = None
        while True:
            page = self.io.list_files(
                max_entries=2,
                cursor=cursor,
                file_glob="*.txt",
                max_scanned_entries=3,
            )
            txt_files.extend(page["files"])
            cursor = page["nextCursor"]
            if cursor is None:
                break
        self.assertEqual(9, len(txt_files))
        self.assertTrue(all(path.endswith(".txt") for path in txt_files))
        after = {
            path.name: path.read_bytes()
            for path in self.workspace.repository.iterdir() if path.is_file()
        }
        self.assertEqual(before, after)

    def test_listing_response_budget_preserves_every_path_across_pages(self):
        names = [f"file-{index:03d}-{'p' * 90}.txt" for index in range(110)]
        for name in names:
            (self.workspace.repository / name).write_text("x", encoding="utf-8")
        pages = []
        cursor = None
        while True:
            page = self.io.list_files(max_entries=500, cursor=cursor)
            pages.append(page)
            self.assertLessEqual(sum(len(json.dumps(path))
                                     for path in page["files"]), 8_000)
            cursor = page["nextCursor"]
            if cursor is None:
                break
        self.assertEqual("RESPONSE_BUDGET", pages[0]["truncationReason"])
        self.assertFalse(pages[0]["complete"])
        self.assertTrue(pages[0]["moreExists"])
        self.assertEqual(names, sorted(path for page in pages for path in page["files"]))
        self.assertEqual(len(names), len({path for page in pages for path in page["files"]}))
        self.assertTrue(pages[-1]["complete"])

    def test_listing_oversized_single_path_is_bounded_and_cursor_progresses(self):
        oversized_name = "x" * 8_100 + ".txt"
        for name in ("first.txt", "later.txt", "last.txt"):
            (self.workspace.repository / name).write_text("x", encoding="utf-8")
        entries = [(self.workspace.repository / name, True)
                   for name in ("first.txt", oversized_name, "later.txt", "last.txt")]
        with patch("autonomous_oss_remediation_agent.capabilities.workspace_io._walk_repository_entries",
                   side_effect=lambda directory: iter(entries)):
            pages = []
            cursor = None
            for _ in range(5):
                page = self.io.list_files(max_entries=2, cursor=cursor, file_glob="*.txt")
                pages.append(page)
                self.assertLess(len(json.dumps(page)), 8_000)
                cursor = page["nextCursor"]
                if cursor is None:
                    break
            else:
                self.fail("Oversized path prevented listing cursor progress")

        first = pages[0]
        self.assertEqual(["first.txt"], first["files"])
        self.assertEqual(1, len(first["oversizedEntries"]))
        summary = first["oversizedEntries"][0]
        self.assertTrue(summary["pathTruncated"])
        self.assertEqual(len(oversized_name), summary["pathChars"])
        self.assertEqual(1, summary["resultIndex"])
        self.assertTrue(first["pathDetailsOmitted"])
        self.assertTrue(first["moreExists"])
        self.assertEqual(["first.txt", "later.txt", "last.txt"],
                         [name for page in pages for name in page["files"]])
        self.assertEqual(4, pages[-1]["totalMatches"])

    def test_search_response_budget_preserves_every_match_across_pages(self):
        path = self.workspace.repository / "matches.txt"
        path.write_text("\n".join(f"needle-{index:03d}-" + "x" * 490
                                  for index in range(35)), encoding="utf-8")
        second_path = self.workspace.repository / "z-matches.txt"
        second_path.write_text("\n".join(f"needle-{index:03d}-" + "y" * 490
                                         for index in range(20)), encoding="utf-8")
        pages = []
        cursor = None
        while True:
            page = self.io.search_text("needle", max_results=100, cursor=cursor)
            pages.append(page)
            self.assertLessEqual(sum(len(json.dumps(match))
                                     for match in page["results"]), 8_000)
            cursor = page["nextCursor"]
            if cursor is None:
                break
        self.assertEqual("RESPONSE_BUDGET", pages[0]["truncationReason"])
        self.assertFalse(pages[0]["complete"])
        self.assertTrue(pages[0]["moreExists"])
        self.assertEqual(([('matches.txt', line) for line in range(1, 36)] +
                          [('z-matches.txt', line) for line in range(1, 21)]),
                         [(match["path"], match["line"]) for page in pages
                          for match in page["results"]])
        self.assertTrue(pages[-1]["complete"])

    def test_small_listing_and_search_remain_complete(self):
        (self.workspace.repository / "small.txt").write_text("needle\n", encoding="utf-8")
        listing = self.io.list_files()
        search = self.io.search_text("needle")
        self.assertEqual(["small.txt"], listing["files"])
        self.assertIsNone(listing["nextCursor"])
        self.assertTrue(listing["complete"])
        self.assertFalse(listing["moreExists"])
        self.assertEqual(1, len(search["results"]))
        self.assertIsNone(search["nextCursor"])
        self.assertTrue(search["complete"])
        self.assertFalse(search["moreExists"])

    def test_file_listing_excludes_git_files_and_directories(self):
        git_directory = self.workspace.repository / ".git"
        git_directory.mkdir()
        (git_directory / "config").write_text("hidden", encoding="utf-8")
        module = self.workspace.repository / "module"
        module.mkdir()
        (module / ".git").write_text("gitdir: ../metadata", encoding="utf-8")
        (module / "visible.txt").write_text("visible", encoding="utf-8")
        (self.workspace.repository / ".m2" / "repository").mkdir(parents=True)
        (self.workspace.repository / ".m2" / "repository" / "cached.pom").write_text(
            "cache", encoding="utf-8"
        )
        (self.workspace.repository / "target").mkdir()
        (self.workspace.repository / "target" / "generated.txt").write_text(
            "generated", encoding="utf-8"
        )
        (self.workspace.repository / ".mvn").mkdir()
        (self.workspace.repository / ".mvn" / "maven.config").write_text(
            "-T1C\n", encoding="utf-8"
        )

        files = []
        cursor = None
        while True:
            page = self.io.list_files(max_entries=1, cursor=cursor, max_scanned_entries=2)
            files.extend(page["files"])
            cursor = page["nextCursor"]
            if cursor is None:
                break

        self.assertEqual([".mvn/maven.config", "module/visible.txt"], files)
        self.assertFalse(any(part == ".git" for path in files for part in Path(path).parts))

    def test_authoritative_runtime_state_is_outside_repository(self):
        script = (
            "import json,os; print(json.dumps({name: os.environ.get(name) "
            "for name in ('HOME','USERPROFILE','TEMP','TMPDIR')}))"
        )
        authoritative = self.runner.run_agent_shell(f'{sys.executable} -c "{script}"')

        self.assertTrue(authoritative.succeeded, authoritative.stderr)
        environment = json.loads(authoritative.stdout)
        for name in ("HOME", "USERPROFILE", "TEMP", "TMPDIR"):
            value = Path(environment[name]).resolve()
            self.assertNotEqual(self.workspace.repository.resolve(), value)
            self.assertNotIn(self.workspace.repository.resolve(), value.parents)

    def test_listing_cursor_completion_and_eviction_close_resources(self):
        for index in range(5):
            (self.workspace.repository / f"item-{index}.txt").write_text(
                str(index), encoding="utf-8"
            )
        io = WorkspaceIO(
            self.workspace,
            self.trace,
            max_active_listing_cursors=2,
        )

        first_page = io.list_files(max_entries=1, max_scanned_entries=1)
        completed_cursor = first_page["nextCursor"]
        completed_state = io._listing_cursors[completed_cursor]
        cursor = completed_cursor
        while cursor is not None:
            page = io.list_files(max_entries=10, cursor=cursor, max_scanned_entries=20)
            cursor = page["nextCursor"]
        self.assertNotIn(completed_cursor, io._listing_cursors)
        self.assertIsNone(completed_state.iterator.gi_frame)
        with self.assertRaisesRegex(ValueError, "completed listing cursor"):
            io.list_files(cursor=completed_cursor)

        first = io.list_files(max_entries=1, max_scanned_entries=1)["nextCursor"]
        first_state = io._listing_cursors[first]
        second = io.list_files(max_entries=1, max_scanned_entries=1)["nextCursor"]
        third = io.list_files(max_entries=1, max_scanned_entries=1)["nextCursor"]
        self.assertEqual(2, len(io._listing_cursors))
        self.assertNotIn(first, io._listing_cursors)
        self.assertIn(second, io._listing_cursors)
        self.assertIn(third, io._listing_cursors)
        self.assertIsNone(first_state.iterator.gi_frame)
        with self.assertRaisesRegex(ValueError, "evicted"):
            io.list_files(cursor=first)
        for active_cursor in tuple(io._listing_cursors):
            io._close_listing_cursor(active_cursor)
        self.assertEqual({}, io._listing_cursors)

    def test_pre_intent_mutation_and_shell_are_isolated_then_active_routing_switches(self):
        changed = False
        (self.workspace.repository / "existing-shell.txt").write_text(
            "authoritative\n", encoding="utf-8"
        )
        journal = JournalLifecycle(
            JournalStore(self.trace), self.trace, "contract", lambda: changed
        )
        journal.begin_cycle(1)
        capabilities = DeveloperCapabilitySet(self.io, self.runner, self.budget, self.trace, journal)
        experiment = capabilities.begin_cycle(1)
        (experiment.repository / "capture_environment.py").write_text(
            "import json, os\n"
            "from pathlib import Path\n"
            "names = ('HOME', 'TMPDIR')\n"
            "Path('runtime-environment.json').write_text(json.dumps({name: os.environ[name] for name in names}))\n",
            encoding="utf-8",
        )

        edit = capabilities.edit_workspace_text("write", "isolated.txt", content="experiment")
        deleted_experiment = capabilities.delete_workspace_file("existing-shell.txt")
        self.assertEqual("experimental", deleted_experiment["workspaceKind"])
        self.assertTrue((self.workspace.repository / "existing-shell.txt").is_file())
        capabilities.edit_workspace_text("write", "existing-shell.txt", content="restored")
        shell = capabilities.run_workspace_shell(
            "Set-Content shell.txt experiment; Set-Content existing-shell.txt modified"
            if os.name == "nt"
            else "printf experiment > shell.txt; printf modified > existing-shell.txt"
        )

        self.assertEqual("ok", edit["status"])
        self.assertEqual(0, shell["exitCode"])
        self.assertTrue((experiment.repository / "isolated.txt").is_file())
        self.assertTrue((experiment.repository / "shell.txt").is_file())
        self.assertEqual(
            "modified",
            (experiment.repository / "existing-shell.txt").read_text(encoding="utf-8").strip(),
        )
        self.assertFalse((self.workspace.repository / "isolated.txt").exists())
        self.assertFalse((self.workspace.repository / "shell.txt").exists())
        self.assertEqual(
            "authoritative\n",
            (self.workspace.repository / "existing-shell.txt").read_text(encoding="utf-8"),
        )
        environment_result = capabilities.run_workspace_shell("python capture_environment.py")
        self.assertEqual(0, environment_result["exitCode"])
        experimental_environment = json.loads(
            (experiment.repository / "runtime-environment.json").read_text(encoding="utf-8")
        )
        experimental_runtime = self.workspace.temp / "experimental-runtime" / "cycle-1"
        self.assertEqual(
            (experimental_runtime / "home").resolve(),
            Path(experimental_environment["HOME"]).resolve(),
        )
        self.assertEqual(
            (experimental_runtime / "temp").resolve(),
            Path(experimental_environment["TMPDIR"]).resolve(),
        )
        tooling = capabilities.run_workspace_shell(
            "python -c \"from pathlib import Path; Path('tooling.txt').write_text('ok')\"; "
            "git init; git config user.name Experiment"
        )
        self.assertEqual(0, tooling["exitCode"])
        self.assertEqual("ok", (experiment.repository / "tooling.txt").read_text(encoding="utf-8"))
        self.assertTrue((experiment.repository / ".git" / "config").is_file())
        self.assertFalse((self.workspace.repository / "tooling.txt").exists())
        self.assertFalse((self.workspace.repository / ".git").exists())
        authoritative_target = self.workspace.repository / "absolute-escape.txt"
        authoritative_target.write_text("authoritative\n", encoding="utf-8")
        absolute_escape = capabilities.run_workspace_shell(
            f"Set-Content '{authoritative_target}' escape"
            if os.name == "nt"
            else f"printf escape > '{authoritative_target}'"
        )
        relative_escape = capabilities.run_workspace_shell(
            "Set-Content ../../../repository/relative-escape.txt escape"
            if os.name == "nt"
            else "printf escape > ../../../repository/relative-escape.txt"
        )
        indirect_escape = capabilities.run_workspace_shell(
            "$parts = @('..', '..', '..', 'repository', 'indirect-escape.txt'); "
            "$target = [IO.Path]::GetFullPath((Join-Path $PWD ($parts -join '\\'))); "
            "try { Set-Content $target escape -ErrorAction Stop } "
            "catch { Set-Content indirect-attempt-ran.txt caught }"
            if os.name == "nt"
            else "python -c \"import errno; from pathlib import Path; p=Path.cwd(); "
            "target=p.joinpath(*(['..']*3+['repository','indirect-escape.txt'])).resolve(); "
            "\ntry: target.write_text('escape')\nexcept OSError as error:\n "
            "if not isinstance(error, PermissionError) and error.errno != errno.EROFS: raise\n "
            "(p/'indirect-attempt-ran.txt').write_text(str(error.errno))\""
        )
        self.assertFalse(absolute_escape["blocked"])
        self.assertFalse(relative_escape["blocked"])
        self.assertFalse(indirect_escape["blocked"])
        self.assertEqual("authoritative\n", authoritative_target.read_text(encoding="utf-8"))
        self.assertFalse((self.workspace.repository / "relative-escape.txt").exists())
        self.assertFalse((self.workspace.repository / "indirect-escape.txt").exists())
        self.assertTrue((experiment.repository / "indirect-attempt-ran.txt").is_file())
        denied = capabilities.edit_workspace_text(
            "write", "forbidden.txt", content="no", workspace="authoritative"
        )
        self.assertEqual("PHASE_CAPABILITY_UNAVAILABLE", denied["failureCode"])
        answers = _valid_intent_answers()
        submission = capabilities.submit_cycle_intent(1, answers)
        self.assertEqual("accepted", submission["status"])
        self.assertEqual("EXECUTION", submission["phase"])
        self.assertIn("edit_workspace_text", submission["availableCapabilities"])
        self.assertIn("run_workspace_shell", submission["availableCapabilities"])
        self.assertIn("this cycle", submission["nextAction"])
        self.assertFalse(journal.cycles[1].late_intent)
        self.assertEqual((), capabilities.execution_activity(1))
        authoritative_shell = capabilities.run_workspace_shell(
            "Set-Content authoritative-shell.txt real"
            if os.name == "nt"
            else "printf real > authoritative-shell.txt"
        )
        experimental_shell = capabilities.run_workspace_shell(
            "Set-Content execution-experiment.txt probe"
            if os.name == "nt"
            else "printf probe > execution-experiment.txt",
            workspace="experiment",
        )
        self.assertEqual(0, authoritative_shell["exitCode"])
        self.assertEqual(0, experimental_shell["exitCode"])
        self.assertTrue((self.workspace.repository / "authoritative-shell.txt").is_file())
        self.assertTrue((experiment.repository / "execution-experiment.txt").is_file())
        self.assertFalse((self.workspace.repository / "execution-experiment.txt").exists())
        capabilities.edit_workspace_text("write", "authoritative.txt", content="real")
        capabilities.edit_workspace_text(
            "write", "further-experiment.txt", content="probe", workspace="experiment"
        )
        self.assertTrue((self.workspace.repository / "authoritative.txt").is_file())
        self.assertTrue((experiment.repository / "further-experiment.txt").is_file())
        self.assertFalse((self.workspace.repository / "further-experiment.txt").exists())
        journal.require_outcome()
        self.assertEqual(frozenset({"submit_cycle_outcome", "retrieve_retained_evidence"}), capabilities.available_tool_names())
        denied = capabilities.edit_workspace_text("write", "outcome.txt", content="blocked")
        self.assertEqual("PHASE_CAPABILITY_UNAVAILABLE", denied["failureCode"])
        denied_shell = capabilities.run_workspace_shell(
            "Set-Content outcome-shell.txt blocked"
            if os.name == "nt"
            else "printf blocked > outcome-shell.txt"
        )
        self.assertEqual("PHASE_CAPABILITY_UNAVAILABLE", denied_shell["failureCode"])

    def test_current_experimental_shell_cannot_mutate_historical_cycle_workspace(self):
        if not self.runner.experimental_isolation.available:
            self.skipTest("No experimental process isolation backend on this platform")
        first = self.workspace.fork_repository(1)
        self.runner.prepare_experimental_workspace(first)
        historical_file = first.repository / "historical.txt"
        historical_file.write_text("cycle-one\n", encoding="utf-8")
        second = self.workspace.fork_repository(2)
        self.runner.prepare_experimental_workspace(second)

        result = self.runner.run_agent_shell(
            "try { Set-Content ../../cycle-1/repository/historical.txt changed -ErrorAction Stop } "
            "catch { Set-Content historical-attempt-ran.txt caught }"
            if os.name == "nt"
            else "(printf changed > ../../cycle-1/repository/historical.txt) || printf caught > historical-attempt-ran.txt",
            repository_workspace=second,
        )

        self.assertFalse(result.blocked)
        self.assertTrue((second.repository / "historical-attempt-ran.txt").is_file())
        self.assertEqual("cycle-one\n", historical_file.read_text(encoding="utf-8"))

    def test_experimental_shell_cannot_mutate_authoritative_file_through_symlink_or_reparse_point(self):
        if not self.runner.experimental_isolation.available:
            self.skipTest("No experimental process isolation backend on this platform")
        experiment = self.workspace.fork_repository(1)
        self.runner.prepare_experimental_workspace(experiment)
        authoritative_directory = self.workspace.repository / "symlink-target"
        authoritative_directory.mkdir()
        authoritative_target = authoritative_directory / "target.txt"
        authoritative_target.write_text("authoritative\n", encoding="utf-8")
        symlink_path = experiment.repository / "authoritative-link"
        if os.name == "nt":
            created = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(symlink_path), str(authoritative_directory)],
                capture_output=True,
                text=True,
                check=False,
            )
            if created.returncode != 0:
                self.skipTest("Directory reparse-point creation is unavailable on this host")
        else:
            try:
                os.symlink(authoritative_directory, symlink_path, target_is_directory=True)
            except OSError:
                self.skipTest("Symlink creation is unavailable on this host")

        result = self.runner.run_agent_shell(
            "python -c \"import errno; from pathlib import Path; "
            "target=Path('authoritative-link/target.txt'); marker=Path('symlink-attempt-ran.txt'); "
            "\ntry: target.write_text('escape')\nexcept OSError as error:\n "
            "if not isinstance(error, PermissionError) and error.errno != errno.EROFS: raise\n "
            "marker.write_text(str(error.errno))\"",
            repository_workspace=experiment,
        )

        self.assertFalse(result.blocked)
        self.assertTrue((experiment.repository / "symlink-attempt-ran.txt").is_file())
        self.assertEqual("authoritative\n", authoritative_target.read_text(encoding="utf-8"))

    def test_linux_mount_namespace_backend_runs_real_tools_and_blocks_proc_root_alias(self):
        if self.runner.experimental_isolation.backend != "linux-user-mount-namespace":
            self.skipTest("Linux user and mount namespace backend is not selected on this host")
        experiment = self.workspace.fork_repository(1)
        existing = experiment.repository / "existing.txt"
        existing.write_text("before\n", encoding="utf-8")
        authoritative = self.workspace.repository / "protected.txt"
        authoritative.write_text("authoritative\n", encoding="utf-8")
        self.runner.prepare_experimental_workspace(experiment)

        child_script = experiment.repository / "child.py"
        child_script.write_text(
            "import os\n"
            "from pathlib import Path\n"
            "Path('existing.txt').write_text('after\\n')\n"
            "Path('child-created.txt').write_text('child\\n')\n"
            "Path(os.environ['TMPDIR'], 'child-temp.txt').write_text('temp\\n')\n",
            encoding="utf-8",
        )
        proc_alias = Path("/proc/1/root") / authoritative.relative_to("/")
        (experiment.repository / "attack.py").write_text(
            "import os\n"
            "from pathlib import Path\n"
            f"targets = [Path({str(authoritative)!r}), Path({str(proc_alias)!r})]\n"
            "denied = 0\n"
            "for target in targets:\n"
            "    try:\n"
            "        target.write_text('escape')\n"
            "    except OSError:\n"
            "        denied += 1\n"
            "if denied != len(targets):\n"
            "    raise SystemExit(1)\n"
            f"try:\n    os.link({str(authoritative)!r}, 'hardlink-alias')\n"
            "except OSError:\n    pass\n"
            "else:\n    raise SystemExit(1)\n"
            "Path('attacks-denied.txt').write_text('denied\\n')\n",
            encoding="utf-8",
        )
        command = "python child.py && git init && git status --short && python attack.py"
        result = self.runner.run_agent_shell(command, repository_workspace=experiment)

        self.assertEqual(0, result.exit_code)
        self.assertEqual("after\n", existing.read_text(encoding="utf-8"))
        self.assertEqual(
            "child\n",
            (experiment.repository / "child-created.txt").read_text(encoding="utf-8"),
        )
        self.assertTrue((experiment.repository / ".git").is_dir())
        self.assertTrue((experiment.repository / "attacks-denied.txt").is_file())
        self.assertFalse((experiment.repository / "hardlink-alias").exists())
        self.assertTrue(
            (
                self.workspace.temp
                / "experimental-runtime"
                / "cycle-1"
                / "temp"
                / "child-temp.txt"
            ).is_file()
        )
        self.assertEqual("authoritative\n", authoritative.read_text(encoding="utf-8"))

    def test_cycle_forks_preserve_exact_current_authoritative_working_state(self):
        _git(self.workspace.repository, "init", "-b", "main")
        (self.workspace.repository / "tracked.txt").write_text("base\n", encoding="utf-8")
        (self.workspace.repository / "deleted.txt").write_text("remove\n", encoding="utf-8")
        _git(self.workspace.repository, "add", ".")
        _git(self.workspace.repository, "-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-m", "base")
        (self.workspace.repository / "tracked.txt").write_text("cycle-one-current\n", encoding="utf-8")
        (self.workspace.repository / "untracked.txt").write_text("untracked\n", encoding="utf-8")
        (self.workspace.repository / "deleted.txt").unlink()

        first = self.workspace.fork_repository(1)
        self.assertEqual(
            self.workspace.investigation / "cycle-1" / "repository",
            first.repository,
        )
        self.assertEqual("cycle-one-current\n", (first.repository / "tracked.txt").read_text(encoding="utf-8"))
        self.assertEqual("untracked\n", (first.repository / "untracked.txt").read_text(encoding="utf-8"))
        self.assertFalse((first.repository / "deleted.txt").exists())
        self.assertTrue((first.repository / ".git").is_dir())

        (first.repository / "tracked.txt").write_text("abandoned experiment\n", encoding="utf-8")
        (self.workspace.repository / "tracked.txt").write_text("accepted remediation\n", encoding="utf-8")
        second = self.workspace.fork_repository(2)
        self.assertEqual("accepted remediation\n", (second.repository / "tracked.txt").read_text(encoding="utf-8"))
        self.assertNotEqual(
            (first.repository / "tracked.txt").read_text(encoding="utf-8"),
            (second.repository / "tracked.txt").read_text(encoding="utf-8"),
        )

    def test_scanner_uses_harness_configuration_and_selected_workspace(self):
        scanner = _RecordingScanner()
        journal = JournalLifecycle(JournalStore(self.trace), self.trace, "contract", lambda: False)
        journal.begin_cycle(1)
        capabilities = DeveloperCapabilitySet(
            self.io, self.runner, self.budget, self.trace, journal, scanner, ("HIGH",)
        )
        experiment = capabilities.begin_cycle(1)
        before = capabilities.scan_current_repository()
        self.assertEqual("experimental", before["workspaceKind"])
        self.assertEqual("COMPLETED_CLEAN", before["outcome"])
        self.assertEqual(0, before["findingCount"])
        self.assertEqual([], before["findings"])
        self.assertTrue(before["findingsComplete"])
        self.assertFalse(before["findingDetailsOmitted"])
        self.assertTrue(before["complete"])
        self.assertFalse(before["moreExists"])
        self.assertIsNotNone(before["evidenceReference"])
        self.assertIsNotNone(before["rawEvidenceReference"])
        self.assertEqual((experiment.repository, ("HIGH",)), scanner.calls[0][:2])
        capabilities.submit_cycle_intent(1, _valid_intent_answers())
        after = capabilities.scan_current_repository()
        self.assertEqual("authoritative", after["workspaceKind"])
        self.assertEqual(self.workspace.repository, scanner.calls[1][0])

    def test_standard_cycle_environment_is_prepared_retained_and_reported(self):
        capabilities = DeveloperCapabilitySet(self.io, self.runner, self.budget, self.trace)
        experiment = capabilities.begin_cycle(1)
        reported = capabilities.experimental_environment_for_model()
        variables = reported["variables"]
        runtime = self.workspace.temp / "experimental-runtime" / "cycle-1"
        self.assertEqual(runtime / "home", Path(variables["HOME"]))
        self.assertEqual(runtime / "temp", Path(variables["TMPDIR"]))
        self.assertTrue((runtime / "home").is_dir())
        self.assertTrue((runtime / "temp").is_dir())
        self.assertEqual(variables, self.runner.experimental_environment(experiment))
        evidence = self.trace.execution_environment(experiment.repository)
        self.assertEqual({"isolated-runtime-root", "standard-home", "standard-temp"},
                         {resource["kind"] for resource in evidence["resources"]})

    def test_explicit_scan_resource_is_confined_and_never_replaced(self):
        scanner = _RecordingScanner()
        journal = JournalLifecycle(JournalStore(self.trace), self.trace, "contract", lambda: False)
        journal.begin_cycle(1)
        capabilities = DeveloperCapabilitySet(self.io, self.runner, self.budget, self.trace, journal, scanner)
        experiment = capabilities.begin_cycle(1)
        runtime = self.workspace.temp / "experimental-runtime" / "cycle-1"
        selected = runtime / "temp" / "chosen-cache"
        selected.mkdir()
        (selected / "marker").write_text("resource", encoding="utf-8")
        valid = capabilities.scan_current_repository(runtime_resource_path=str(selected))
        self.assertEqual("ok", valid["status"])
        self.assertEqual(selected.resolve(), scanner.calls[-1][3])
        call_count = len(scanner.calls)
        missing = capabilities.scan_current_repository(runtime_resource_path=str(runtime / "temp" / "missing"))
        self.assertEqual("RUNTIME_RESOURCE_INVALID", missing["failureCode"])
        outside = capabilities.scan_current_repository(runtime_resource_path=str(self.workspace.repository))
        self.assertEqual("RUNTIME_RESOURCE_INVALID", outside["failureCode"])
        capabilities.submit_cycle_intent(1, _valid_intent_answers())
        authoritative = capabilities.scan_current_repository(runtime_resource_path=str(selected))
        self.assertEqual("RUNTIME_RESOURCE_INVALID", authoritative["failureCode"])
        self.assertEqual(call_count, len(scanner.calls))
        self.assertFalse((self.workspace.repository / "marker").exists())
        self.assertEqual(experiment.repository, scanner.calls[0][0])
        self.assertIn("runtime_resource_path omitted", authoritative["repairInstructions"])
        self.assertIn("not the authoritative", authoritative["error"])
        repaired = capabilities.scan_current_repository(workspace="authoritative")
        self.assertEqual("ok", repaired["status"])
        self.assertEqual(self.workspace.repository, scanner.calls[-1][0])
        self.assertIsNone(scanner.calls[-1][3])
        self.assertEqual(call_count + 1, len(scanner.calls))

    def test_command_created_runtime_resource_reaches_experimental_scan(self):
        scanner = _RecordingScanner()
        journal = JournalLifecycle(JournalStore(self.trace), self.trace, "contract", lambda: False)
        journal.begin_cycle(1)
        capabilities = DeveloperCapabilitySet(self.io, self.runner, self.budget, self.trace, journal, scanner)
        experiment = capabilities.begin_cycle(1)
        script = experiment.repository / "create_runtime.py"
        script.write_text(
            "import os\nfrom pathlib import Path\n"
            "p = Path(os.environ['TMPDIR']) / 'created-cache'\n"
            "p.mkdir()\n(p / 'marker').write_text('ready')\n",
            encoding="utf-8",
        )
        command = capabilities.run_workspace_shell("python create_runtime.py")
        self.assertEqual(0, command["exitCode"], command)
        resource = Path(capabilities.experimental_environment_for_model()["variables"]["TMPDIR"]) / "created-cache"
        result = capabilities.scan_current_repository(runtime_resource_path=str(resource))
        self.assertEqual("ok", result["status"])
        self.assertEqual(resource.resolve(), scanner.calls[-1][3])
        self.assertFalse(resource.is_relative_to(experiment.repository))
        self.assertFalse(resource.is_relative_to(self.workspace.repository))
        self.assertEqual("ready", (resource / "marker").read_text(encoding="utf-8"))

    def test_explicit_file_deletion_routes_to_authoritative_only_after_intent(self):
        (self.workspace.repository / "remove.txt").write_text("authoritative", encoding="utf-8")
        journal = JournalLifecycle(JournalStore(self.trace), self.trace, "contract", lambda: False)
        journal.begin_cycle(1)
        capabilities = DeveloperCapabilitySet(self.io, self.runner, self.budget, self.trace, journal)
        experiment = capabilities.begin_cycle(1)
        before = capabilities.delete_workspace_file("remove.txt")
        self.assertEqual("experimental", before["workspaceKind"])
        self.assertFalse((experiment.repository / "remove.txt").exists())
        self.assertTrue((self.workspace.repository / "remove.txt").exists())
        self.assertEqual("accepted", capabilities.submit_cycle_intent(1, _valid_intent_answers())["status"])
        after = capabilities.delete_workspace_file("remove.txt")
        self.assertEqual("authoritative", after["workspaceKind"])
        self.assertFalse((self.workspace.repository / "remove.txt").exists())
        self.assertIn("delete_workspace_file", journal.cycles[1].authoritative_activity)

    def test_logical_tmp_scan_resource_maps_to_current_cycle_only(self):
        scanner = _RecordingScanner()
        journal = JournalLifecycle(JournalStore(self.trace), self.trace, "contract", lambda: False)
        journal.begin_cycle(1)
        capabilities = DeveloperCapabilitySet(self.io, self.runner, self.budget, self.trace, journal, scanner)
        first = capabilities.begin_cycle(1)
        selected = self.workspace.temp / "experimental-runtime" / "cycle-1" / "temp" / "chosen-cache"
        selected.mkdir()
        with patch.object(type(self.runner.experimental_isolation), "backend", new_callable=PropertyMock, return_value="linux-user-mount-namespace"):
            self.assertEqual(selected.resolve(), self.runner.resolve_experimental_runtime_resource(first, "/tmp/chosen-cache"))
            self.assertEqual("ok", capabilities.scan_current_repository(runtime_resource_path="/tmp/chosen-cache")["status"])
            self.assertEqual(selected.resolve(), scanner.calls[-1][3])
            second = capabilities.begin_cycle(2)
            with self.assertRaisesRegex(ValueError, "does not exist"):
                self.runner.resolve_experimental_runtime_resource(second, "/tmp/chosen-cache")

    def test_research_is_replaceable_truthful_phase_gated_and_budgeted(self):
        provider = _FakeResearchProvider()
        journal = JournalLifecycle(JournalStore(self.trace), self.trace, "contract", lambda: False)
        journal.begin_cycle(1)
        capabilities = DeveloperCapabilitySet(
            self.io, self.runner, self.budget, self.trace, journal,
            research_provider=provider,
        )
        capabilities.begin_cycle(1)
        search = capabilities.research_search("current advisory")
        fetch = capabilities.research_fetch("https://example.test/advisory")
        self.assertEqual("success", search["status"])
        self.assertEqual("http_network_failure", fetch["status"])
        self.assertEqual(2, self.budget.tool_calls)
        self.assertTrue(search["complete"])
        self.assertEqual("{", capabilities.retrieve_retained_evidence(search["resultReference"], max_bytes=1)["content"])
        artifacts = sorted((self.workspace.artifacts / "research").glob("*.json"))
        self.assertEqual(2, len(artifacts))
        events = [json.loads(line) for line in self.trace.events_path.read_text(encoding="utf-8").splitlines()]
        research_events = [event for event in events if event["type"] == "research"]
        self.assertEqual(2, len(research_events))
        self.assertTrue(all(event.get("resultReference") for event in research_events))
        capabilities.submit_cycle_intent(1, _valid_intent_answers())
        journal.require_outcome()
        denied = capabilities.research_search("not allowed now")
        self.assertEqual("PHASE_CAPABILITY_UNAVAILABLE", denied["failureCode"])
        self.assertEqual(["current advisory"], provider.queries)

    def test_http_research_provider_reports_unavailable_and_blocked_truthfully(self):
        unavailable = HttpResearchProvider(enabled=False).search("anything")
        blocked = HttpResearchProvider(enabled=True).fetch("http://127.0.0.1/private")
        self.assertEqual(ResearchStatus.UNAVAILABLE, unavailable.status)
        self.assertIn("Network disabled", unavailable.error)
        self.assertEqual(ResearchStatus.BLOCKED, blocked.status)
        self.assertIn("non-public", blocked.error)

    def test_http_research_accepts_xml_and_retains_raw_source(self):
        from email.message import Message

        class Response:
            def __init__(self, media_type, body):
                self.headers = Message()
                self.headers["Content-Type"] = media_type
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def geturl(self):
                return "https://repo.example.test/source"

            def read(self, limit):
                return self.body[:limit]

        class Opener:
            response = None

            def open(self, request, timeout):
                return self.response

        opener = Opener()
        provider = HttpResearchProvider(enabled=True)
        with patch("autonomous_oss_remediation_agent.capabilities.research.socket.getaddrinfo",
                   return_value=[(None, None, None, None, ("93.184.215.14", 443))]), \
             patch("autonomous_oss_remediation_agent.capabilities.research.build_opener", return_value=opener):
            opener.response = Response("text/xml", b"<project><version>1.2</version></project>")
            xml = provider.fetch("https://repo.example.test/source")
            self.assertEqual(ResearchStatus.SUCCESS, xml.status)
            self.assertIn("<version>1.2</version>", xml.content)
            self.assertEqual("text/xml", xml.media_type)
            capabilities = DeveloperCapabilitySet(self.io, self.runner, self.budget, self.trace,
                                                   research_provider=provider)
            fetched = capabilities.research_fetch("https://repo.example.test/source")
            self.assertTrue(fetched["acquisitionSucceeded"])
            self.assertTrue(fetched["extractionSucceeded"])
            self.assertEqual("<project><version>1.2</version></project>",
                             capabilities.retrieve_retained_evidence(fetched["rawEvidenceReference"])["content"])
            opener.response = Response("image/png", b"\x89PNG")
            unsupported = provider.fetch("https://repo.example.test/source")
            self.assertEqual(ResearchStatus.EXTRACTION_FAILURE, unsupported.status)
            self.assertTrue(unsupported.raw_bytes_b64)
            failed = capabilities.research_fetch("https://repo.example.test/source")
            self.assertFalse(failed["extractionSucceeded"])
            self.assertTrue(failed["acquisitionSucceeded"])
            self.assertFalse(failed["complete"])
            opener.response = Response("text/plain", b"X" * 1001)
            limited = HttpResearchProvider(enabled=True, max_response_bytes=1000)
            truncated = limited.fetch("https://repo.example.test/source")
            self.assertTrue(truncated.truncated)
            self.assertEqual(1000, len(truncated.content))

    def test_research_uses_shared_tool_budget(self):
        budget = ExecutionBudget(
            ExecutionBudgetConfig(max_tool_calls=1, overall_timeout_seconds=30)
        )
        provider = _FakeResearchProvider()
        capabilities = DeveloperCapabilitySet(
            self.io, self.runner, budget, self.trace, research_provider=provider
        )
        self.assertEqual("success", capabilities.research_search("first")["status"])
        exhausted = capabilities.research_search("second")
        self.assertEqual("EXECUTION_BUDGET_EXCEEDED", exhausted["failureCode"])
        self.assertEqual(["first"], provider.queries)

    def test_research_failure_metadata_and_retained_prefix_reach_model(self):
        import base64
        from tests.unit.test_research_acquisition import Response
        provider = HttpResearchProvider(enabled=True, max_response_bytes=1000)
        challenge = b'<form id="challenge-form" action="/anomaly.js">human challenge</form>'
        result = provider._read_response(Response(challenge), 200)
        with patch.object(provider, "search", return_value=result):
            capabilities = DeveloperCapabilitySet(self.io, self.runner, self.budget, self.trace,
                                                   research_provider=provider)
            blocked = capabilities.research_search("current releases")
        self.assertEqual("blocked", blocked["status"])
        self.assertFalse(blocked["complete"])
        self.assertTrue(blocked["acquisitionSucceeded"])
        self.assertFalse(blocked["extractionSucceeded"])
        self.assertEqual([], blocked["results"])
        self.assertNotIn("raw_bytes_b64", blocked)
        self.assertIn("Do not retry", blocked["recovery"])
        self.assertEqual(challenge.decode(), capabilities.retrieve_retained_evidence(blocked["rawEvidenceReference"])["content"])
        source = b"<style>" + b"x" * 1500 + b"</style><p>fact</p>"
        with patch.object(provider, "_retrieve", return_value=provider._read_response(Response(source), 200)):
            truncated = capabilities.research_fetch("https://example.test/large")
        self.assertEqual("source_truncated", truncated["status"])
        self.assertTrue(truncated["sourceTruncated"])
        self.assertFalse(truncated["moreExists"])  # The missing source tail was never retained.
        self.assertFalse(truncated["complete"])
        self.assertFalse(truncated["extractionSucceeded"])
        retained = json.loads(self.trace.resolve_evidence_reference(truncated["resultReference"]).read_text())
        self.assertEqual(source[:1000], base64.b64decode(retained["result"]["raw_bytes_b64"]))
        self.assertEqual(1000, retained["result"]["acquired_bytes"])

    def test_research_retains_full_extracted_result_while_returning_excerpt(self):
        class LargeProvider:
            def search(self, query):
                return ResearchResult(ResearchStatus.SUCCESS, "research",
                                      results=tuple({"title": str(i), "url": f"https://example.test/{i}"}
                                                    for i in range(25)))

            def fetch(self, url):
                return ResearchResult(ResearchStatus.SUCCESS, url, content="Q" * 12000)

        capabilities = DeveloperCapabilitySet(self.io, self.runner, self.budget, self.trace,
                                               research_provider=LargeProvider())
        search = capabilities.research_search("advisory")
        fetch = capabilities.research_fetch("https://example.test")
        self.assertEqual(10, len(search["results"]))
        self.assertFalse(search["complete"])
        self.assertEqual(4000, len(fetch["content"]))
        self.assertTrue(fetch["moreExists"])
        search_detail = capabilities.retrieve_retained_evidence(search["resultReference"], query='"title": "24"')
        self.assertTrue(search_detail["matches"])
        fetch_detail = capabilities.retrieve_retained_evidence(fetch["resultReference"], query="QQQQ")
        self.assertTrue(fetch_detail["matches"])

    def test_pre_checkpoint_evidence_survives_session_replacement(self):
        from autonomous_oss_remediation_agent.orchestrator import AutonomousRemediationOrchestrator
        path = self.trace.write_text("research/pre-intent.txt", "Observed source before failed checkpoint")
        self.trace.append_event("research", cycle=1, operation="fetch", resultReference=str(path))
        references = AutonomousRemediationOrchestrator._retained_evidence_index(self.trace, 1)
        self.assertEqual(1, len(references))
        replacement = DeveloperCapabilitySet(self.io, self.runner, self.budget, self.trace)
        retrieved = replacement.retrieve_retained_evidence(references[0]["reference"])
        self.assertEqual("Observed source before failed checkpoint", retrieved["content"])

    def test_recovery_manifest_keeps_older_sources_addressable(self):
        from autonomous_oss_remediation_agent.orchestrator import AutonomousRemediationOrchestrator
        for index in range(31):
            path = self.trace.write_text(f"research/source-{index}.txt", f"source {index}")
            self.trace.append_event("research", cycle=1, operation="fetch", resultReference=str(path))
        references = AutonomousRemediationOrchestrator._retained_evidence_index(self.trace, 1)
        self.assertEqual(30, len(references))
        manifest = self.capabilities.retrieve_retained_evidence(references[0]["reference"])
        self.assertIn("source-0.txt", manifest["content"])

    def test_research_search_bounds_long_fields_but_retains_them(self):
        long_title = "T" * 5000 + "TITLE-END"
        long_url = "https://example.test/" + "u" * 5000 + "URL-END"

        class LongFieldProvider:
            def search(self, query):
                return ResearchResult(ResearchStatus.SUCCESS, "research",
                                      results=({"title": long_title, "url": long_url},
                                               {"title": "界" * 1000, "url": "https://example.test/" + "界" * 1000}))

            def fetch(self, url):
                raise AssertionError("fetch was not requested")

        capabilities = DeveloperCapabilitySet(self.io, self.runner, self.budget, self.trace,
                                               research_provider=LongFieldProvider())
        result = capabilities.research_search("advisory")
        self.assertEqual(200, len(result["results"][0]["title"]))
        self.assertEqual(500, len(result["results"][0]["url"]))
        self.assertLessEqual(len(json.dumps(result["results"][1]["title"])), 202)
        self.assertLessEqual(len(json.dumps(result["results"][1]["url"])), 502)
        self.assertTrue(result["resultFieldsOmitted"])
        self.assertFalse(result["complete"])
        self.assertTrue(result["moreExists"])
        retained = self.trace.resolve_evidence_reference(result["resultReference"]).read_text(encoding="utf-8")
        self.assertIn(long_title, retained)
        self.assertIn(long_url, retained)

    def test_new_package_has_no_reference_agent_imports(self):
        package_root = Path(__file__).resolve().parents[2] / "autonomous_oss_remediation_agent"
        for path in package_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("from oss_remediation_agent", text, path)
            self.assertNotIn("import oss_remediation_agent", text, path)

def _valid_intent_answers():
    return typed_intent_answers([
        {"section": "Problem understanding in project context", "answer": "Resolve the supplied Task to Solve completely in the observed project context."},
        {
            "section": "Information, investigation and remaining uncertainty",
            "answer": """| Information needed | Why it was needed | Sources examined | Finding | What remains unknown or requires execution |
|---|---|---|---|---|
| Ownership | Choose a change | pom.xml | A property owns it | Execution checks remain |

### Material assumptions that remain necessary

None.""",
        },
        {
            "section": "Project-applicable engineering synthesis and high-level solution space",
            "answer": "Repository evidence identifies one project-applicable control boundary and one supported high-level approach; no alternative is manufactured.",
        },
        {
            "section": "Concrete candidate solutions",
            "answer": """#### Candidate Solution A — Focused change
| Question | Model answer |
|---|---|
| What exact solution is proposed? | Update the owned value. |
| Why were these exact changes selected? | Evidence supports the owner. |
| What evidence supports the expected result? | Repository inspection. |
| Which parts of the problem will it resolve? | All requested scope. |
| Does it satisfy every applicable requirement? | Yes. |
| How will it be implemented? | Edit and validate. |
| How will compatibility be preserved? | Run checks. |
| Why is the result coherent and maintainable? | One owner remains. |
| What risks or unknowns remain? | Execution evidence. |
| How will the result be validated? | Configured checks. |
| Is it a COMPLETE or PARTIAL solution? | COMPLETE. |""",
        },
        {
            "section": "Selected solution",
            "answer": """- **Selected solution:** Candidate A — Focused change
- **Classification:** COMPLETE
- **Why it is preferred:** Evidence supports it.
- **Comparative coverage:** Complete.
- **Remaining risks:** Execution evidence.
- **Evidence requiring reconsideration:** Contradictory checks.""",
        },
    ])


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


class _RecordingScanner:
    backend = "fake"

    def __init__(self):
        self.calls = []

    def scan(self, repository, severity_scope, label, *, runtime_resource=None):
        from autonomous_oss_remediation_agent.models import ScanReport

        self.calls.append((repository, severity_scope, label, runtime_resource))
        raw = next(parent / "artifacts" / f"{label}.json"
                   for parent in repository.parents if (parent / "artifacts").is_dir())
        raw.write_text("{}", encoding="utf-8")
        return ScanReport(True, (), None, str(raw), backend=self.backend)


class _FakeResearchProvider:
    def __init__(self):
        self.queries = []

    def search(self, query):
        self.queries.append(query)
        return ResearchResult(
            ResearchStatus.SUCCESS,
            "fake-search",
            results=({"title": "Advisory", "url": "https://example.test/advisory"},),
        )

    def fetch(self, url):
        return ResearchResult(
            ResearchStatus.HTTP_NETWORK_FAILURE,
            url,
            error="simulated network failure",
        )


if __name__ == "__main__":
    unittest.main()
