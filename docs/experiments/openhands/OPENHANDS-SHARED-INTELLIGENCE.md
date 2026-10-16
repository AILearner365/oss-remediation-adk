# OpenHands shared optional SBRI stage — M2 Change 4

Status: implemented optional intelligence foundation. Date: 2026-10-16.

This change adapts the existing Gate-2 Spring Boot Release Intelligence (SBRI)
integration to the shared task lifecycle. It imports the existing applicability,
collector invocation, candidate validation, fingerprint/cache, bounded agent
message and review-bundle retention behavior from
`scripts/openhands/sbri_integration.py` and
`spring_boot_release_intelligence.release_selection`.

No collector, release-ranking, dependency-resolution or remediation logic is
duplicated. Existing Gate-2 scripts and their output remain unchanged.

## Trusted internal invocation

There is no public execution endpoint. A trusted internal worker invokes the
stage only after a successful durable baseline has entered `INTELLIGENCE`:

```python
from pathlib import Path

from openhands_shared import (
    IntelligenceConfig,
    IntelligenceProfile,
    SharedIntelligenceAssessor,
)

profile = IntelligenceProfile(
    profile_id="gate2-sbri-v1",
    task_agent_profile="gate2-dependency-remediation-v1",
    control_repo=Path("/srv/oss-remediation-adk"),
    scanner=Path("/opt/approved/osv-scanner"),
    release_ranges="4.0.x",
    max_candidates=4,
)
record = SharedIntelligenceAssessor(
    store,
    IntelligenceConfig(
        artifact_root=Path("/durable/openhands-artifacts"),
        profiles=(profile,),
    ),
).assess(task_id)
```

Candidate versions/ranges, limits, scanner and SBRI configuration paths are
deployment-owned profile values. They are not accepted from task metadata. An
invalid or missing profile cannot silently fall back to another candidate set.

## Preconditions and repository boundary

The operation requires:

- task state `INTELLIGENCE`;
- an immutable successful baseline assessment;
- complete SHA-256 verification of all baseline artifacts;
- a baseline report whose task, commit and outcome match SQLite metadata; and
- the original clean task worktree, exact baseline commit, task branch and Git
  common-repository identity.

The same Git identity and cleanliness check runs after SBRI. The existing SBRI
source fingerprint must match the current source, and `sourceUnchanged=false`
is treated as repository mutation. SBRI never edits the source repository.

## Outcomes and lifecycle

| Outcome | Meaning | Next task status |
| --- | --- | --- |
| `DISABLED` | Registered task selected `sbri.mode=disabled`; no applicability or collector call. | `AGENT_RUNNING` |
| `NOT_APPLICABLE` | Existing applicability logic found no relevant Spring Boot Maven security task. | `AGENT_RUNNING` |
| `COMPLETE` | Complete validated SBRI evidence and selection manifest are available. | `AGENT_RUNNING` |
| `PARTIAL` | Bounded evidence is usable but explicitly incomplete or inconclusive. | `AGENT_RUNNING` |
| `FAILED` | Operational SBRI failure produced no usable recommendation. | `AGENT_RUNNING` |
| `INVALID_SELECTION` | Approved selection/profile configuration was rejected. | `FAILED_INFRASTRUCTURE` |
| `CORRUPT_EVIDENCE` | Fingerprint, result, manifest or retained evidence was inconsistent. | `FAILED_INFRASTRUCTURE` |
| `REPOSITORY_MUTATION` | Repository identity or source state changed during the stage. | `FAILED_INFRASTRUCTURE` |

`AGENT_RUNNING` means only that the future agent stage is pending. This change
does not create an OpenHands conversation and leaves OpenHands execution status
`NOT_STARTED`.

The `FAILED` continuation matches the frozen Gate-2 behavior: an operationally
unavailable SBRI result is explicit incomplete intelligence, not proof that a
Spring Boot strategy is impossible. Invalid candidate selection still stops
before the model boundary.

## Evidence and reasoning boundary

The durable intelligence record includes applicability, outcome, profile,
fingerprint, resolved selection manifest, evaluated versions, reuse state,
explanation and completion time. Retained artifacts include:

- the canonical shared intelligence record;
- the bounded `<SBRI_PRE_EDIT_EVIDENCE>` summary;
- the existing SBRI `latest.json`, summary and selection manifest;
- complete result JSON and HTML report when available; and
- bounded raw evidence selected by the existing review-bundle retention logic.

Each artifact has a safe relative path, byte count and SHA-256. Maven caches,
materialized candidate workspaces and HTTP caches remain excluded by the
existing retention function.

The summary preserves these rules:

- candidate selection limits evidence collection, not later agent strategies;
- security rank is not an implementation or compatibility decision;
- residual findings are not acceptable final-state exceptions; and
- independent deterministic validation remains authoritative.

## Persistence and recovery

Schema version 4 adds immutable `intelligence_assessments` through an in-place
v3-to-v4 migration. Existing tasks, events, artifacts, preparations and
baselines are retained. Outcome metadata, artifact references, next task status
and the sequenced intelligence event commit in one SQLite transaction.

Files are published without overwriting conflicting content. If a process stops
after artifacts are finalized but before SQLite commit, retry validates the
canonical record and every manifested hash, then commits without invoking SBRI
again. A committed replay verifies all baseline and intelligence artifacts and
returns the existing record without new events.

The existing SBRI fingerprint cache is also preserved inside the task runtime,
so an interruption before the canonical shared record can reuse completed
collector work rather than execute it again.

## Frozen parity and limitations

The shared adapter uses the existing applicability, selection, fingerprint,
summary, prompt wording and review retention functions. Unlike the frozen path,
an explicitly disabled task skips applicability inspection entirely and records
that deliberate decision durably. Shared evidence paths and lifecycle events are
additional product metadata; frozen script output is unchanged.

The shared component is an internal operation, not a worker scheduler. Its lock
is process-local; a production multi-process worker must claim tasks before
calling it to prevent duplicate collector work. The existing collector process
environment and network isolation must be supplied by the deployment runner.

## Offline verification

Tests use temporary Git worktrees, durable baseline fixtures and injected SBRI
collector records. They cover all outcomes above, selection/fingerprint checks,
source mutation, artifact tampering, restart, migration, transaction rollback,
crash reconciliation, task isolation and the absence of real network, model,
OpenHands, Maven, scanner or SBRI invocation.
