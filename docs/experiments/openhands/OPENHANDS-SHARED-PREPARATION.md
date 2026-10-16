# OpenHands shared preparation — M2 Change 2

Status: implemented local preparation foundation. Date: 2026-10-16.

This change implements only deterministic Git identity and worktree preparation
from the sequence in
[OPENHANDS-SHARED-BACKEND-IMPLEMENTATION-PLAN.md](OPENHANDS-SHARED-BACKEND-IMPLEMENTATION-PLAN.md).
It does not run a baseline, Maven, a scanner, SBRI, OpenHands, a model,
validation or delivery. It does not create or update a remote task branch.

## Internal preparation contract

Preparation is available only to a trusted in-process caller. No public HTTP
execution or transition endpoint was added, and `POST /v1/tasks` still only
registers a `QUEUED` task.

```python
from pathlib import Path

from openhands_shared import (
    DeterministicPreparer,
    PreparationConfig,
    SQLiteTaskStore,
    TrustedRepository,
)

store = SQLiteTaskStore(Path("/durable/state/tasks.sqlite3"))
config = PreparationConfig(
    workspace_root=Path("/durable/workspaces"),
    repositories=(
        TrustedRepository(
            repository_url="https://github.com/approved/project.git",
            source_path=Path("/srv/git/project"),
            origin_url="https://github.com/approved/project.git",
        ),
    ),
)
record = DeterministicPreparer(store, config).prepare(task_id)
```

The registered `repository.url` must exactly match one configured logical
repository identity. The source path and its expected `origin` fetch URL are
deployment-owned configuration, not request fields. Credentials and arbitrary
environment variables cannot be supplied by the task.

The immutable preparation record contains:

- task and logical repository identity;
- requested full base ref and expected commit;
- resolved baseline commit, which must equal the expected commit;
- trusted source and isolated workspace paths;
- deterministic local task branch; and
- completion timestamp.

## Git verification and isolation

For an unprepared task the adapter:

1. verifies the configured source is a Git repository with the exact configured
   `origin` and, for a non-bare source, a clean working tree;
2. resolves the full requested ref with `git ls-remote` and requires the remote
   commit to equal the registered full SHA;
3. fetches that ref into a task-owned local namespace only when it is not
   already present, then verifies it resolves to the expected commit;
4. rejects any task-owned ref or branch already pointing somewhere else;
5. creates `workspace_root/<taskId>/repository` using `git worktree add` and the
   deterministic local branch `openhands-shared/<taskId>`; and
6. verifies common-repository identity, branch, exact `HEAD` and cleanliness
   before persistence.

The shared source working tree is never checked out, reset or cleaned. Git must
update its common local ref/worktree metadata to create a worktree, but the
adapter never invokes `push`, force-push, remote branch creation, reset, clean,
or deletion. It never removes a conflicting path, branch, ref or worktree.

All Git commands are structured argument arrays selected from a preparation
allowlist. They run with prompts disabled, hooks and filesystem monitoring
disabled, credential helpers and inherited HTTP authorization disabled, a null
global/system configuration boundary, and a small constructed environment that
excludes inherited tokens, passwords and credentials. Repository-local smudge
or process filters are rejected before checkout. Command stdout/stderr is not
persisted or included in exceptions.

## State transitions and persistence

The internal operation owns these transitions only:

```text
QUEUED --preparation.started--> PREPARING
PREPARING --preparation.completed + immutable record--> BASELINING
```

The preparation record, `BASELINING` status and completion event are written in
one SQLite transaction. Entering `BASELINING` means only that preparation is
complete; Change 2 does not start baseline assessment.

Schema version 2 adds `preparations` through an explicit in-place v1→v2
migration. Existing task/event/artifact rows are retained. Database triggers
prevent preparation updates or deletion, and the schema requires expected and
baseline commits to be identical. Workspace paths and local task branches are
unique across tasks.

## Recovery and fail-closed behavior

- A retry after `preparation.started` may complete a pre-existing worktree only
  when repository identity, deterministic path, task branch, exact commit and
  cleanliness all match.
- A retry after durable completion verifies the recorded workspace and returns
  the same record without adding events or worktrees.
- Missing, dirty, symlinked or foreign workspaces; non-empty path collisions;
  moved remote refs; and unexpected local refs/branches fail without reset,
  cleanup or overwrite.
- An unsupported logical repository fails before leaving `QUEUED`.
- A failure after preparation starts remains `PREPARING` for explicit operator
  diagnosis or safe retry. Change 2 does not introduce failure-policy or worker
  orchestration.
- Per-repository locking serializes local common-repository metadata changes.
  POSIX uses an advisory file lock that releases on process exit, plus an
  in-process thread lock.

## Offline verification

Tests use temporary seed repositories, bare remotes, source clones and SQLite
files. They cover exact-ref success, moved and incorrect SHAs, repository
allowlisting and origin identity, dirty/path/branch collisions, concurrent
isolated tasks,
interrupted retry, repeated preparation, absence of remote mutation, restricted
subprocess environment, database restart, atomic completion and schema
migration. Existing API and Gate-2 offline regressions remain separate and
unchanged.

## Remaining boundary

The deployment must provide a trusted local source repository and workspace
volume. Cross-process repository locking currently relies on POSIX advisory
locking; the non-POSIX fallback is process-local and must be strengthened before
a multi-process Windows deployment. Change 2 intentionally has no private-remote
credential adapter; an approved read-only repository identity mechanism is
required before refreshing a private HTTPS origin in deployment.

M2 Change 3 consumes this immutable record through the internal baseline
adapter documented in
[OPENHANDS-SHARED-BASELINE.md](OPENHANDS-SHARED-BASELINE.md). Its exact-commit
and clean-worktree checks remain baseline-entry requirements; later stages use
a separate identity rule for authorized agent modifications.
