from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from autonomous_oss_remediation_agent.capabilities import ExecutionBudget, ProcessRunner
from autonomous_oss_remediation_agent.config import DeliveryConfig, ExecutionBudgetConfig, RuntimePolicy
from autonomous_oss_remediation_agent.deterministic.git_auth import GitCredential, NonInteractiveGitAuth
from autonomous_oss_remediation_agent.deterministic.repository import (
    RepositoryPreparationError,
    RepositoryPreparer,
)
from autonomous_oss_remediation_agent.integrations.delivery import GitHubRestDeliveryAdapter
from autonomous_oss_remediation_agent.models import CommandResult
from autonomous_oss_remediation_agent.workspace import RunWorkspace, TraceStore


class _RecordingRunner:
    def __init__(
        self,
        *,
        clone_exit_code: int = 0,
        checkout_fails_once: bool = False,
        fetch_exit_code: int = 0,
    ):
        self.clone_exit_code = clone_exit_code
        self.checkout_fails_once = checkout_fails_once
        self.fetch_exit_code = fetch_exit_code
        self.calls: list[dict[str, object]] = []
        self.repository: Path | None = None
        self.origin_url = ""

    def run_argv(self, command, **kwargs):
        source = kwargs.get("source", "deterministic")
        environment = dict(kwargs.get("environment", {}))
        self.calls.append(
            {
                "command": list(command),
                "display_command": list(kwargs.get("display_command", command)),
                "source": source,
                "environment": environment,
                "redact_values": tuple(kwargs.get("redact_values", ())),
            }
        )
        exit_code = 0
        stdout = ""
        if source == "repository_clone":
            exit_code = self.clone_exit_code
            if exit_code == 0:
                self.repository = Path(command[-1])
                self.repository.mkdir(parents=True, exist_ok=True)
                self.origin_url = command[-2]
                self._write_config()
        elif source == "repository_clean_origin":
            self.origin_url = command[-1]
            self._write_config()
        elif source == "repository_checkout" and self.checkout_fails_once:
            self.checkout_fails_once = False
            exit_code = 1
        elif source == "repository_fetch_ref":
            exit_code = self.fetch_exit_code
        elif source == "repository_metadata" and "rev-parse" in command:
            stdout = "abc123\n"
        elif source == "repository_metadata" and "get-url" in command:
            stdout = f"{self.origin_url}\n"
        return CommandResult(
            list(kwargs.get("display_command", command)),
            str(kwargs.get("cwd", ".")),
            exit_code,
            stdout=stdout,
        )

    def call(self, source: str) -> dict[str, object]:
        return next(call for call in self.calls if call["source"] == source)

    def _write_config(self) -> None:
        if self.repository is None:
            return
        git_directory = self.repository / ".git"
        git_directory.mkdir(exist_ok=True)
        (git_directory / "config").write_text(
            f'[remote "origin"]\n\turl = {self.origin_url}\n',
            encoding="utf-8",
        )


class NonInteractiveGitAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = RunWorkspace.create(self.temp.name, "run")
        self.trace = TraceStore(self.workspace)

    def tearDown(self):
        self.temp.cleanup()

    def test_public_clone_without_token_is_noninteractive(self):
        runner = _RecordingRunner()

        metadata = RepositoryPreparer(self.workspace, runner, self.trace, {}).clone(
            "https://github.com/example/repo.git", "main"
        )

        call = runner.call("repository_clone")
        self._assert_noninteractive(call)
        self.assertNotIn("GIT_ASKPASS_SECRET", call["environment"])
        self.assertIn("https://github.com/example/repo.git", call["command"])
        self.assertEqual("https://github.com/example/repo.git", metadata.remote_url)

    def test_authenticated_clone_uses_temporary_url_and_restores_clean_origin(self):
        token = "github-secret-token"
        runner = _RecordingRunner()

        metadata = RepositoryPreparer(
            self.workspace,
            runner,
            self.trace,
            {
                "GH_TOKEN": token,
                "GITHUB_TOKEN": "lower-priority-token",
                "HOME": "corporate-home",
                "USERPROFILE": "corporate-profile",
                "GIT_CONFIG_GLOBAL": "corporate.gitconfig",
            },
        ).clone("https://github.com/example/repo.git", "main")

        call = runner.call("repository_clone")
        self._assert_noninteractive(call)
        actual_command = " ".join(call["command"])
        display_command = " ".join(call["display_command"])
        self.assertIn(
            f"https://x-access-token:{token}@github.com/example/repo.git",
            actual_command,
        )
        self.assertIn(
            "https://x-access-token:[REDACTED]@github.com/example/repo.git",
            display_command,
        )
        self.assertNotIn(token, display_command)
        self.assertIn(token, call["redact_values"])
        self.assertNotIn("GH_TOKEN", call["environment"])
        self.assertNotIn("GITHUB_TOKEN", call["environment"])
        self.assertEqual("corporate-home", call["environment"]["HOME"])
        self.assertEqual("corporate-profile", call["environment"]["USERPROFILE"])
        self.assertEqual("corporate.gitconfig", call["environment"]["GIT_CONFIG_GLOBAL"])
        self.assertNotIn("GIT_CONFIG_NOSYSTEM", call["environment"])
        self.assertEqual("https://github.com/example/repo.git", metadata.remote_url)
        self.assertNotIn(token, metadata.remote_url)
        config = (self.workspace.repository / ".git" / "config").read_text(encoding="utf-8")
        self.assertIn("https://github.com/example/repo.git", config)
        self.assertNotIn(token, config)
        self.assertNotIn(token, self.trace.events_path.read_text(encoding="utf-8"))

    def test_fetch_uses_same_noninteractive_auth(self):
        token = "github-secret-token"
        runner = _RecordingRunner(checkout_fails_once=True)

        RepositoryPreparer(self.workspace, runner, self.trace, {"GITHUB_TOKEN": token}).clone(
            "https://github.com/example/repo.git", "feature"
        )

        call = runner.call("repository_fetch_ref")
        self._assert_noninteractive(call)
        self.assertIn(
            f"https://x-access-token:{token}@github.com/example/repo.git",
            " ".join(call["command"]),
        )
        self.assertNotIn(token, " ".join(call["display_command"]))
        config = (self.workspace.repository / ".git" / "config").read_text(encoding="utf-8")
        self.assertIn("https://github.com/example/repo.git", config)
        self.assertNotIn(token, config)

    def test_failed_fetch_reports_fetch_result(self):
        runner = _RecordingRunner(checkout_fails_once=True, fetch_exit_code=128)

        with self.assertRaises(RepositoryPreparationError) as raised:
            RepositoryPreparer(self.workspace, runner, self.trace, {}).clone(
                "https://github.com/example/repo.git", "missing-reference"
            )

        self.assertIsNotNone(raised.exception.result)
        self.assertEqual(128, raised.exception.result.exit_code)
        self.assertIn("fetch", raised.exception.result.command)
        self.assertNotIn("checkout", raised.exception.result.command)

    def test_failed_github_clone_without_token_fails_deterministically(self):
        runner = _RecordingRunner(clone_exit_code=128)

        with self.assertRaisesRegex(RepositoryPreparationError, "GH_TOKEN or GITHUB_TOKEN"):
            RepositoryPreparer(self.workspace, runner, self.trace, {}).clone(
                "https://github.com/example/private.git", "main"
            )

        self._assert_noninteractive(runner.call("repository_clone"))

    def test_delivery_push_uses_shared_noninteractive_auth(self):
        token = "github-secret-token"
        runner = _RecordingRunner()
        adapter = GitHubRestDeliveryAdapter(DeliveryConfig(), object(), runner, self.trace)
        self.workspace.repository.mkdir()
        git_directory = self.workspace.repository / ".git"
        git_directory.mkdir()
        config_path = git_directory / "config"
        clean_url = "https://github.com/example/repo.git"
        config_path.write_text(f'[remote "origin"]\n\turl = {clean_url}\n', encoding="utf-8")

        result = adapter._push(
            self.workspace,
            clean_url,
            "remediation-branch",
            GitCredential(token),
        )

        self.assertTrue(result.succeeded)
        call = runner.call("delivery_push")
        self._assert_noninteractive(call)
        self.assertIn(
            f"https://x-access-token:{token}@github.com/example/repo.git",
            " ".join(call["command"]),
        )
        self.assertNotIn(token, " ".join(call["display_command"]))
        self.assertNotIn(token, " ".join(result.command))
        self.assertIn("[REDACTED]", " ".join(result.command))
        self.assertIn("core.hooksPath=", " ".join(call["command"]))
        self.assertEqual(f'[remote "origin"]\n\turl = {clean_url}\n', config_path.read_text(encoding="utf-8"))

    def test_process_runner_redacts_secret_from_results_artifacts_and_trace(self):
        token = "github-secret-token"
        runner = ProcessRunner(
            self.workspace,
            self.trace,
            ExecutionBudget(ExecutionBudgetConfig(command_timeout_seconds=30)),
            RuntimePolicy(),
        )
        environment = os.environ.copy()
        environment["GIT_ASKPASS_SECRET"] = token

        result = runner.run_argv(
            [
                sys.executable,
                "-c",
                "import sys; print(sys.argv[1]); print(sys.argv[1], file=sys.stderr)",
                token,
            ],
            environment=environment,
            redact_values=(token,),
            display_command=[sys.executable, "-c", "<redacted-test>", "[REDACTED]"],
            source="credential_redaction",
        )

        self.assertTrue(result.succeeded)
        self.assertNotIn(token, result.stdout)
        self.assertNotIn(token, result.stderr)
        self.assertNotIn(token, Path(result.stdout_artifact).read_text(encoding="utf-8"))
        self.assertNotIn(token, Path(result.stderr_artifact).read_text(encoding="utf-8"))
        self.assertNotIn(token, self.trace.events_path.read_text(encoding="utf-8"))
        self.assertNotIn(token, " ".join(result.command))

    def test_github_rest_failures_do_not_expose_token(self):
        token = "github-secret-token"

        class Response:
            status_code = 401

            @staticmethod
            def json():
                return {"message": f"rejected {token}"}

        adapter = GitHubRestDeliveryAdapter(
            DeliveryConfig(),
            object(),
            _RecordingRunner(),
            self.trace,
            http_post=lambda *args, **kwargs: Response(),
        )
        response = adapter._create_pull_request(
            "example/repo", "branch", "main", "title", "body", GitCredential(token)
        )
        self.assertNotIn(token, str(response))

        def fail(*args, **kwargs):
            raise RuntimeError(token)

        adapter.http_post = fail
        response = adapter._create_pull_request(
            "example/repo", "branch", "main", "title", "body", GitCredential(token)
        )
        self.assertNotIn(token, str(response))

    def _assert_noninteractive(self, call: dict[str, object]) -> None:
        command = call["command"]
        environment = call["environment"]
        self.assertEqual("0", environment["GIT_TERMINAL_PROMPT"])
        self.assertEqual("never", environment["GCM_INTERACTIVE"])
        self.assertEqual("generic", environment["GCM_PROVIDER"])
        self.assertNotIn("GIT_ASKPASS", environment)
        self.assertNotIn("GIT_ASKPASS_SECRET", environment)
        self.assertIn("credential.helper=", command)
        self.assertIn("credential.interactive=false", command)
        self.assertIn("credential.modalPrompt=false", command)


if __name__ == "__main__":
    unittest.main()
