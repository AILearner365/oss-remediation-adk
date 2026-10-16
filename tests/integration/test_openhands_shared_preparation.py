from __future__ import annotations

import concurrent.futures
import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openhands_shared.contracts import TaskRequest, TaskStatus
from openhands_shared.preparation import (
    DeterministicPreparer,
    GitRunner,
    PreparationConfig,
    ReferenceMismatchError,
    RepositoryIdentityError,
    TrustedRepository,
    UnsupportedRepositoryError,
    WorkspaceConflictError,
    branch_for_task,
)
from openhands_shared.store import SQLiteTaskStore
from tests.openhands_shared_fixtures import task_request_data


LOGICAL_REPOSITORY = "https://github.com/example/maven-app.git"


class SharedPreparationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.seed = self.root / "seed"
        self.remote = self.root / "remote.git"
        self.source = self.root / "source"
        self.workspaces = self.root / "workspaces"
        self.database = self.root / "state" / "tasks.sqlite3"

        self._git("init", "-b", "main", str(self.seed))
        self._git("-C", str(self.seed), "config", "user.name", "Preparation Test")
        self._git("-C", str(self.seed), "config", "user.email", "preparation@example.invalid")
        (self.seed / "README.md").write_text("baseline\n", encoding="utf-8")
        self._git("-C", str(self.seed), "add", "README.md")
        self._git("-C", str(self.seed), "commit", "-m", "baseline")
        self.baseline = self._git("-C", str(self.seed), "rev-parse", "HEAD").stdout.strip()
        self._git("clone", "--bare", str(self.seed), str(self.remote))
        self._git("-C", str(self.seed), "remote", "add", "origin", str(self.remote))
        self._git("clone", str(self.remote), str(self.source))

        self.store = SQLiteTaskStore(self.database)
        self.git = GitRunner()
        self.config = PreparationConfig(
            workspace_root=self.workspaces,
            repositories=(
                TrustedRepository(
                    repository_url=LOGICAL_REPOSITORY,
                    source_path=self.source,
                    origin_url=str(self.remote),
                ),
            ),
        )
        self.preparer = DeterministicPreparer(self.store, self.config, git=self.git)

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_prepares_exact_commit_without_remote_or_source_worktree_mutation(self):
        task_id = self._register("correct")
        remote_before = self._remote_refs()
        source_status_before = self._git(
            "-C", str(self.source), "status", "--porcelain=v1", "--untracked-files=all"
        ).stdout

        record = self.preparer.prepare(task_id)

        self.assertEqual(self.baseline, record.baseline_commit)
        self.assertEqual(self.baseline, self._git("-C", record.workspace_path, "rev-parse", "HEAD").stdout.strip())
        self.assertEqual(
            f"refs/heads/{branch_for_task(task_id)}",
            self._git("-C", record.workspace_path, "symbolic-ref", "HEAD").stdout.strip(),
        )
        self.assertEqual(TaskStatus.BASELINING, self.store.get_status(task_id).status)
        self.assertEqual(record, self.store.get_preparation(task_id))
        self.assertEqual(
            ["task.registered", "preparation.started", "preparation.completed"],
            [event.type for event in self.store.list_events(task_id)],
        )
        self.assertEqual(remote_before, self._remote_refs())
        self.assertEqual(
            source_status_before,
            self._git("-C", str(self.source), "status", "--porcelain=v1", "--untracked-files=all").stdout,
        )

    def test_remote_branch_moved_after_registration_fails_closed(self):
        task_id = self._register("moved")
        (self.seed / "README.md").write_text("moved\n", encoding="utf-8")
        self._git("-C", str(self.seed), "add", "README.md")
        self._git("-C", str(self.seed), "commit", "-m", "move remote")
        self._git("-C", str(self.seed), "push", "origin", "refs/heads/main:refs/heads/main")

        with self.assertRaisesRegex(ReferenceMismatchError, "does not match"):
            self.preparer.prepare(task_id)

        self.assertEqual(TaskStatus.PREPARING, self.store.get_status(task_id).status)
        self.assertIsNone(self.store.get_preparation(task_id))
        self.assertFalse(self.preparer.workspace_for_task(task_id).exists())

    def test_incorrect_expected_commit_fails_before_workspace_creation(self):
        task_id = self._register("incorrect", expected_commit="b" * 40)

        with self.assertRaises(ReferenceMismatchError):
            self.preparer.prepare(task_id)

        self.assertFalse(self.preparer.workspace_for_task(task_id).exists())
        self.assertIsNone(self.store.get_preparation(task_id))

    def test_unsupported_repository_never_enters_preparing(self):
        task_id = self._register(
            "unsupported",
            repository_url="https://github.com/example/not-approved.git",
        )
        empty_config = PreparationConfig(workspace_root=self.workspaces, repositories=())

        with self.assertRaises(UnsupportedRepositoryError):
            DeterministicPreparer(self.store, empty_config).prepare(task_id)

        self.assertEqual(TaskStatus.QUEUED, self.store.get_status(task_id).status)

    def test_configured_source_origin_mismatch_fails_identity_check(self):
        task_id = self._register("origin-mismatch")
        mismatched = PreparationConfig(
            workspace_root=self.workspaces,
            repositories=(
                TrustedRepository(
                    repository_url=LOGICAL_REPOSITORY,
                    source_path=self.source,
                    origin_url=str(self.root / "different-remote.git"),
                ),
            ),
        )

        with self.assertRaisesRegex(RepositoryIdentityError, "origin"):
            DeterministicPreparer(self.store, mismatched).prepare(task_id)

        self.assertFalse(self.preparer.workspace_for_task(task_id).exists())
        self.assertIsNone(self.store.get_preparation(task_id))

    def test_dirty_source_and_workspace_path_conflicts_fail_closed(self):
        dirty_task = self._register("dirty-source")
        (self.source / "untracked.txt").write_text("unexpected\n", encoding="utf-8")
        with self.assertRaisesRegex(RepositoryIdentityError, "dirty"):
            self.preparer.prepare(dirty_task)
        (self.source / "untracked.txt").unlink()

        collision_task = self._register("path-collision")
        collision = self.preparer.workspace_for_task(collision_task)
        collision.mkdir(parents=True)
        (collision / "unexpected.txt").write_text("do not overwrite\n", encoding="utf-8")
        with self.assertRaises(WorkspaceConflictError):
            self.preparer.prepare(collision_task)
        self.assertEqual("do not overwrite\n", (collision / "unexpected.txt").read_text(encoding="utf-8"))

    def test_repository_local_checkout_filter_is_rejected_without_execution(self):
        task_id = self._register("checkout-filter")
        marker = self.root / "filter-was-executed"
        self._git(
            "-C",
            str(self.source),
            "config",
            "filter.untrusted.smudge",
            f"touch {marker}",
        )

        with self.assertRaisesRegex(RepositoryIdentityError, "checkout filters"):
            self.preparer.prepare(task_id)

        self.assertFalse(marker.exists())
        self.assertFalse(self.preparer.workspace_for_task(task_id).exists())

    def test_branch_collision_and_dirty_prepared_workspace_are_not_reset(self):
        collision_task = self._register("branch-collision")
        self._git("-C", str(self.source), "config", "user.name", "Preparation Test")
        self._git("-C", str(self.source), "config", "user.email", "preparation@example.invalid")
        self._git("-C", str(self.source), "commit", "--allow-empty", "-m", "local collision")
        collision_commit = self._git("-C", str(self.source), "rev-parse", "HEAD").stdout.strip()
        self.assertNotEqual(self.baseline, collision_commit)
        self._git("-C", str(self.source), "branch", branch_for_task(collision_task), collision_commit)

        with self.assertRaisesRegex(WorkspaceConflictError, "unexpected commit"):
            self.preparer.prepare(collision_task)
        self.assertEqual(
            collision_commit,
            self._git("-C", str(self.source), "rev-parse", branch_for_task(collision_task)).stdout.strip(),
        )

        clean_task = self._register("dirty-prepared")
        record = self.preparer.prepare(clean_task)
        dirty_file = Path(record.workspace_path) / "dirty.txt"
        dirty_file.write_text("preserve me\n", encoding="utf-8")
        with self.assertRaisesRegex(WorkspaceConflictError, "dirty"):
            self.preparer.prepare(clean_task)
        self.assertEqual("preserve me\n", dirty_file.read_text(encoding="utf-8"))

    def test_concurrent_tasks_create_distinct_isolated_worktrees(self):
        task_ids = [self._register(f"concurrent-{index}") for index in range(6)]

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            records = list(executor.map(self.preparer.prepare, task_ids))

        self.assertEqual(6, len({record.workspace_path for record in records}))
        self.assertEqual(6, len({record.local_branch for record in records}))
        self.assertTrue(all(record.baseline_commit == self.baseline for record in records))
        self.assertTrue(all(self.store.get_status(task_id).status is TaskStatus.BASELINING for task_id in task_ids))

    def test_interrupted_preparation_reconciles_existing_exact_worktree(self):
        task_id = self._register("interrupted")
        self.store.start_preparation(task_id)
        workspace = self.preparer.workspace_for_task(task_id)
        workspace.parent.mkdir(parents=True)
        branch = branch_for_task(task_id)
        self._git(
            "-C",
            str(self.source),
            "worktree",
            "add",
            "-b",
            branch,
            str(workspace),
            self.baseline,
        )

        record = self.preparer.prepare(task_id)

        self.assertEqual(str(workspace), record.workspace_path)
        self.assertEqual(TaskStatus.BASELINING, self.store.get_status(task_id).status)
        self.assertEqual(1, sum(event.type == "preparation.started" for event in self.store.list_events(task_id)))
        self.assertEqual(1, sum(event.type == "preparation.completed" for event in self.store.list_events(task_id)))

    def test_repeated_preparation_is_idempotent_without_duplicate_worktree(self):
        task_id = self._register("repeat")
        first = self.preparer.prepare(task_id)
        worktrees_before = self._worktree_paths()
        events_before = self.store.list_events(task_id)

        second = self.preparer.prepare(task_id)

        self.assertEqual(first, second)
        self.assertEqual(worktrees_before, self._worktree_paths())
        self.assertEqual(events_before, self.store.list_events(task_id))

    def test_preparation_survives_database_close_and_process_style_reopen(self):
        task_id = self._register("restart")
        first = self.preparer.prepare(task_id)
        self.store.close()
        self.store = SQLiteTaskStore(self.database)
        self.preparer = DeterministicPreparer(self.store, self.config, git=GitRunner())

        second = self.preparer.prepare(task_id)

        self.assertEqual(first, second)
        self.assertEqual(TaskStatus.BASELINING, self.store.get_status(task_id).status)

    def test_git_execution_is_array_based_secret_free_and_never_pushes(self):
        task_id = self._register("command-boundary")
        original_run = subprocess.run
        observed: list[tuple[object, dict[str, str]]] = []

        def inspect_run(command, *args, **kwargs):
            observed.append((command, dict(kwargs.get("env", {}))))
            return original_run(command, *args, **kwargs)

        with patch("openhands_shared.preparation.subprocess.run", side_effect=inspect_run):
            self.preparer.prepare(task_id)

        self.assertTrue(observed)
        for command, environment in observed:
            self.assertIsInstance(command, list)
            self.assertNotIn("push", command)
            self.assertFalse(
                any(
                    marker in name.upper()
                    for name in environment
                    for marker in ("TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "API_KEY")
                )
            )
        operations = {invocation.operation for invocation in self.git.history}
        self.assertNotIn("maven", " ".join(operations).lower())
        self.assertNotIn("scanner", " ".join(operations).lower())
        self.assertNotIn("model", " ".join(operations).lower())
        self.assertEqual({"refs/heads/main"}, set(self._remote_refs()))

    def _register(
        self,
        suffix: str,
        *,
        expected_commit: str | None = None,
        repository_url: str = LOGICAL_REPOSITORY,
    ) -> str:
        request = TaskRequest.from_dict(
            task_request_data(
                idempotency_key=f"preparation-{suffix}",
                repository_url=repository_url,
                expected_commit=expected_commit or self.baseline,
            )
        )
        return self.store.register_task(request).status.task_id

    def _remote_refs(self) -> dict[str, str]:
        output = self._git(
            "--git-dir",
            str(self.remote),
            "for-each-ref",
            "--format=%(refname) %(objectname)",
        ).stdout
        return dict(line.split(" ", 1) for line in output.splitlines() if line)

    def _worktree_paths(self) -> tuple[str, ...]:
        output = self._git("-C", str(self.source), "worktree", "list", "--porcelain").stdout
        return tuple(
            line[len("worktree ") :]
            for line in output.splitlines()
            if line.startswith("worktree ")
        )

    @staticmethod
    def _git(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            check=True,
            text=True,
            capture_output=True,
            env={"PATH": os.defpath, "LANG": "C", "LC_ALL": "C"},
        )


class SharedPreparationSchemaMigrationTests(unittest.TestCase):
    def test_v1_database_migrates_in_place_and_preserves_registered_task(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "tasks.sqlite3"
            store = SQLiteTaskStore(database)
            task_id = store.register_task(TaskRequest.from_dict(task_request_data())).status.task_id
            store.close()
            connection = sqlite3.connect(database)
            try:
                connection.executescript(
                    """
                    DROP TRIGGER baseline_assessments_immutable_update;
                    DROP TRIGGER baseline_assessments_immutable_delete;
                    DROP TABLE baseline_assessments;
                    DROP TRIGGER preparations_immutable_update;
                    DROP TRIGGER preparations_immutable_delete;
                    DROP TABLE preparations;
                    UPDATE schema_info SET version = 1 WHERE singleton = 1;
                    """
                )
                connection.commit()
            finally:
                connection.close()

            reopened = SQLiteTaskStore(database)
            try:
                self.assertEqual(task_id, reopened.get_status(task_id).task_id)
                self.assertIsNone(reopened.get_preparation(task_id))
                connection = sqlite3.connect(database)
                try:
                    version = connection.execute(
                        "SELECT version FROM schema_info WHERE singleton = 1"
                    ).fetchone()[0]
                    preparation_table = connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'preparations'"
                    ).fetchone()
                    baseline_table = connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'baseline_assessments'"
                    ).fetchone()
                finally:
                    connection.close()
                self.assertEqual(3, version)
                self.assertEqual(("preparations",), preparation_table)
                self.assertEqual(("baseline_assessments",), baseline_table)
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
