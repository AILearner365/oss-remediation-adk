# OpenHands shared deterministic baseline — M2 Change 3

Status: implemented baseline and durable evidence foundation. Date: 2026-10-16.

This change implements only the deterministic baseline stage described in
[OPENHANDS-SHARED-BACKEND-IMPLEMENTATION-PLAN.md](OPENHANDS-SHARED-BACKEND-IMPLEMENTATION-PLAN.md).
It reuses the existing Maven, scanner, execution-budget, trace and constraint
components used by `scripts/openhands/openhands-gate2-baseline.py`. The frozen
script and its JSON contract remain unchanged.

It does not run SBRI, OpenHands, Gemini, Vertex AI, remediation, independent
validation or delivery. It does not push or otherwise mutate a remote Git ref.

## Trusted internal invocation

There is no public execution endpoint. A trusted worker or offline test invokes
the operation in process after Change 2 has durably prepared the task:

```python
from pathlib import Path

from autonomous_oss_remediation_agent.config import MavenConfig, OsvScannerConfig, ScannerConfig
from openhands_shared import BaselineConfig, BaselineProfile, DeterministicBaselineAssessor

profile = BaselineProfile(
    profile="gate2-dependency-remediation-v1",
    build_commands=("mvn clean verify",),
    maven=MavenConfig(mode="auto"),
    scanner=ScannerConfig(
        backend="osv",
        osv=OsvScannerConfig(
            mode="configured",
            executable="/opt/approved/osv-scanner",
            version="2.6.0",
        ),
    ),
)
record = DeterministicBaselineAssessor(
    store,
    BaselineConfig(
        artifact_root=Path("/durable/openhands-artifacts"),
        profiles=(profile,),
    ),
).assess(task_id)
```

The deployment, not the task, selects the scanner executable, Maven mode,
execution budget and exact approved build-command tuple. The task's requested
commands must exactly match that tuple. Only the approved OSV backend is
accepted by this stage. Processes receive a constructed environment and a
task-local `HOME`; inherited GitHub, model, delivery and other credential
environment values are not passed through.

## Identity and lifecycle

Before tools run, the adapter requires the task to be `BASELINING`, verifies
the immutable preparation record against the registered request, and verifies:

- the worktree and configured source have the same Git common directory;
- the task-owned branch is checked out;
- `HEAD` is exactly the immutable baseline commit; and
- the worktree is clean, including untracked files.

The same check runs after the deterministic tools return. A complete build and
scan with target findings advances atomically:

```text
BASELINING --baseline.completed + metadata + artifact manifest--> INTELLIGENCE
```

`INTELLIGENCE` means only that SBRI is the next pending stage. This change does
not execute it. Build/test failure and a complete scan with no target findings
end in `FAILED_VALIDATION`; an incomplete scan or scanner preflight failure ends
in `FAILED_INFRASTRUCTURE`. These outcomes persist a `baseline.failed` event and
evidence but cannot advance downstream.

Change 2's exact-commit and clean-worktree checks are intentionally not
weakened. Later agent stages must use a different identity rule: verify the
same task-owned worktree/common repository and branch, retain the immutable
baseline as an ancestor, and then assess the authorized modified tree. They
must not reuse this baseline-stage cleanliness or exact-`HEAD` predicate after
the agent has legitimately edited the repository.

## Report and artifacts

The immutable `baseline-report` JSON contains:

- task, repository, ref, branch and exact baseline commit identity;
- assessment status and completion timestamp;
- approved severity scope;
- Maven build/test command results;
- scanner outcome and original vulnerability findings;
- captured Java, Spring Boot and suppression constraints;
- scanner provenance and relevant tool configuration/version data; and
- a manifest of retained runtime evidence artifacts.

The report and command/scanner evidence remain beneath
`artifact_root/<taskId>/baseline/`. Every registered file has a safe relative
path, media type, byte count and SHA-256. Artifact metadata, the immutable
baseline row, task status and sequenced event are committed in one SQLite
transaction. The existing `GET /v1/tasks/{taskId}/artifacts` endpoint exposes
the metadata; artifact content is served by the deployment's authenticated
artifact boundary, not this API.

Schema version 3 adds `baseline_assessments` through an explicit v2-to-v3
migration. Existing task, event, artifact and preparation rows are retained.
Database triggers reject baseline metadata updates and deletion.

## Interruption and recovery

Artifact files are finalized without overwriting an existing path. A process
interruption after report creation but before the SQLite transaction leaves the
task in `BASELINING`; retry validates the report identity and every manifested
hash, commits the existing evidence, and does not rerun completed assessment.
An unexpected existing file, foreign report identity, missing file or checksum
mismatch fails closed. A retry after committed completion verifies all baseline
artifacts and returns the same record without new events or tool execution.

## Offline verification

Tests use temporary local Git repositories/worktrees and injected Maven/scanner
results. They cover successful findings, build failure, incomplete and clean
scans, commit mismatch, dirty workspaces, unapproved commands, artifact hashes,
tampering, interruption recovery, repeat invocation, restart, schema migration,
transaction rollback and concurrent task isolation. These tests make no Maven,
scanner, network, model, SBRI or OpenHands call.

## Gate-2 parity note

The shared adapter preserves the frozen baseline's ordering and meaning:
scanner preflight, `MavenService.run_baseline`, complete OSV assessment,
constraint capture and fail-closed handling. Like the frozen script, a complete
scan with no HIGH/CRITICAL findings does not permit agent work. The shared
adapter additionally persists that outcome and its evidence atomically instead
of exiting with only a process code. The frozen script's output shape and
behavior are unchanged.
