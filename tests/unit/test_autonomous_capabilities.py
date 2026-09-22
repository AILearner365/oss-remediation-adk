from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from google.adk.models import Gemini

from autonomous_oss_remediation_agent.agent import create_remediation_agent
from autonomous_oss_remediation_agent.capabilities import DeveloperCapabilitySet, ExecutionBudget, ProcessRunner, WorkspaceIO
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
                max_tool_calls=8,
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
        with self.assertRaises(WorkspaceBoundaryError):
            self.io.read_text("../outside.txt")
        with self.assertRaises(WorkspaceBoundaryError):
            self.io.read_text(str(Path(self.temp.name).resolve()))
        with self.assertRaises(WorkspaceBoundaryError):
            self.io.edit_text("write", ".git/config", content="bad")

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
                "run_workspace_shell",
                "scan_current_repository",
                "research_search",
                "research_fetch",
                "submit_cycle_intent",
                "submit_cycle_outcome",
            },
            {tool.name for tool in tools},
        )

    def test_one_primary_adk_agent_uses_capability_surface(self):
        agent = create_remediation_agent(self.capabilities, "gemini-2.5-flash")
        self.assertEqual("autonomous_oss_remediation_agent", agent.name)
        self.assertIsInstance(agent.model, Gemini)
        self.assertEqual("gemini-2.5-flash", agent.model.model)
        self.assertEqual(3, agent.model.retry_options.attempts)
        self.assertEqual(1.0, agent.model.retry_options.initial_delay)
        self.assertEqual(8.0, agent.model.retry_options.max_delay)
        self.assertEqual(2.0, agent.model.retry_options.exp_base)
        self.assertEqual(1.0, agent.model.retry_options.jitter)
        self.assertIsNone(agent.model.retry_options.http_status_codes)
        names = {tool.name for tool in agent.tools}
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
        self.assertTrue((self.workspace.investigation / "cycle-1" / "mutated.txt").is_file())

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

    def test_file_listing_excludes_git_files_and_directories(self):
        git_directory = self.workspace.repository / ".git"
        git_directory.mkdir()
        (git_directory / "config").write_text("hidden", encoding="utf-8")
        module = self.workspace.repository / "module"
        module.mkdir()
        (module / ".git").write_text("gitdir: ../metadata", encoding="utf-8")
        (module / "visible.txt").write_text("visible", encoding="utf-8")

        files = []
        cursor = None
        while True:
            page = self.io.list_files(max_entries=1, cursor=cursor, max_scanned_entries=2)
            files.extend(page["files"])
            cursor = page["nextCursor"]
            if cursor is None:
                break

        self.assertEqual(["module/visible.txt"], files)
        self.assertFalse(any(part == ".git" for path in files for part in Path(path).parts))

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
        journal = JournalLifecycle(
            JournalStore(self.trace), self.trace, "contract", lambda: changed
        )
        journal.begin_cycle(1)
        capabilities = DeveloperCapabilitySet(self.io, self.runner, self.budget, self.trace, journal)
        experiment = capabilities.begin_cycle(1)

        edit = capabilities.edit_workspace_text("write", "isolated.txt", content="experiment")
        shell = capabilities.run_workspace_shell("Set-Content shell.txt experiment" if os.name == "nt" else "printf experiment > shell.txt")

        self.assertEqual("ok", edit["status"])
        self.assertEqual(0, shell["exitCode"])
        self.assertTrue((experiment.repository / "isolated.txt").is_file())
        self.assertTrue((experiment.repository / "shell.txt").is_file())
        self.assertFalse((self.workspace.repository / "isolated.txt").exists())
        self.assertFalse((self.workspace.repository / "shell.txt").exists())
        authoritative_target = self.workspace.repository / "absolute-escape.txt"
        absolute_escape = capabilities.run_workspace_shell(
            f"Set-Content '{authoritative_target}' escape"
            if os.name == "nt"
            else f"printf escape > '{authoritative_target}'"
        )
        relative_escape = capabilities.run_workspace_shell(
            "Set-Content ../../repository/relative-escape.txt escape"
            if os.name == "nt"
            else "printf escape > ../../repository/relative-escape.txt"
        )
        self.assertTrue(absolute_escape["blocked"])
        self.assertTrue(relative_escape["blocked"])
        self.assertFalse(authoritative_target.exists())
        self.assertFalse((self.workspace.repository / "relative-escape.txt").exists())
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
        capabilities.edit_workspace_text("write", "authoritative.txt", content="real")
        capabilities.edit_workspace_text(
            "write", "further-experiment.txt", content="probe", workspace="experiment"
        )
        self.assertTrue((self.workspace.repository / "authoritative.txt").is_file())
        self.assertTrue((experiment.repository / "further-experiment.txt").is_file())
        self.assertFalse((self.workspace.repository / "further-experiment.txt").exists())
        journal.require_outcome()
        self.assertEqual(frozenset({"submit_cycle_outcome"}), capabilities.available_tool_names())
        denied = capabilities.edit_workspace_text("write", "outcome.txt", content="blocked")
        self.assertEqual("PHASE_CAPABILITY_UNAVAILABLE", denied["failureCode"])

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
        self.assertEqual((experiment.repository, ("HIGH",)), scanner.calls[0][:2])
        capabilities.submit_cycle_intent(1, _valid_intent_answers())
        after = capabilities.scan_current_repository()
        self.assertEqual("authoritative", after["workspaceKind"])
        self.assertEqual(self.workspace.repository, scanner.calls[1][0])

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

    def test_new_package_has_no_reference_agent_imports(self):
        package_root = Path(__file__).resolve().parents[2] / "autonomous_oss_remediation_agent"
        for path in package_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("from oss_remediation_agent", text, path)
            self.assertNotIn("import oss_remediation_agent", text, path)

def _valid_intent_answers():
    return [
        {"section": "Model understanding", "answer": "Resolve the supplied Task to Solve completely."},
        {
            "section": "Information, investigation and remaining uncertainty",
            "answer": """| Information needed | Why it was needed | Sources examined | Finding | What remains unknown or requires execution |
|---|---|---|---|---|
| Ownership | Choose a change | pom.xml | A property owns it | Execution checks remain |

### Material assumptions that remain necessary

None.""",
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
    ]


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


class _RecordingScanner:
    backend = "fake"

    def __init__(self):
        self.calls = []

    def scan(self, repository, severity_scope, label):
        from autonomous_oss_remediation_agent.models import ScanReport

        self.calls.append((repository, severity_scope, label))
        raw = repository.parent / f"{label}.json"
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
