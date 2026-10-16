# OpenHands shared backend — M1 architecture and incremental implementation plan

Status: M1 proposal; implementation starts only after review. Date: 2026-10-16.

This plan implements, but does not duplicate, the approved lifecycle and gates
in [OPENHANDS-SHARED-EXECUTION-MIGRATION.md](OPENHANDS-SHARED-EXECUTION-MIGRATION.md).
The frozen experiment remains unchanged and runnable throughout migration.

## Smallest useful architecture

```text
REST client        future thin experiment client       Agent Canvas
     \                        |                         /
      \------ product Task API + durable task store ---/
                         |
                    task worker
      PREPARE -> BASELINE -> optional SBRI
                         |
               native OpenHands Agent Server
                 conversation + events
                         |
        Stop Hook -> independent VALIDATE -> recovery
                         |
          PASS-only DELIVERY (M4, separate credentials)
                         |
            durable artifact/object storage
```

There is one product lifecycle and one task contract. UI, REST and experiment
clients submit or observe it; none contains baseline, SBRI, validation or
delivery business logic.

### Native OpenHands responsibilities

- Agent, tools, LLM/provider invocation, condensation and stuck detection.
- Conversation/session identity, execution and continuation.
- Native events, persistence/resume and WebSocket streaming.
- Skills/agent context and Stop Hook execution/feedback transport.
- Workspace API and the Canvas conversation/file/terminal experience.

### Repository integration responsibilities

- Remediation task contract, authorization, idempotency and product status.
- Exact repository/ref resolution, safe task branch/workspace and readiness.
- Deterministic baseline and artifact retention.
- Optional SBRI applicability/evidence and prompt augmentation.
- Construction of the approved OpenHands profile/hook/workspace request.
- Independent validation, attempt policy and acceptance state.
- Durable product events/artifact manifest and restart reconciliation.
- PASS-only, state-hash-checked, idempotent GitHub delivery in M4.
- Experiment evidence export/analysis/publication in the future thin client.

## Proposed repository layout

Follow the existing `autonomous_oss_remediation_agent` package/testing
conventions rather than creating a generic framework:

```text
openhands_shared/
  contracts.py          # versioned task/status/event/result models
  store.py              # task/event/artifact metadata interface + SQLite impl
  lifecycle.py          # explicit stage transitions and reconciliation
  preparation.py        # repository/ref/worktree preparation
  baseline.py           # narrow adapter over current deterministic components
  intelligence.py       # narrow SBRI adapter
  openhands_runtime.py  # native Agent Server client/conversation mapping
  validation.py         # validator + Stop Hook policy adapter
  delivery.py           # added in M4 only
  api.py                # thin HTTP routes
tests/
  unit/test_openhands_shared_*.py
  integration/test_openhands_shared_*.py
```

Names may adjust to existing package import constraints during M2. Do not add a
framework-level plugin registry, general workflow DSL or alternate agent loop.

## Task lifecycle

The product state machine is explicit and monotonic except for documented
recovery transitions:

```text
QUEUED -> PREPARING -> BASELINING -> INTELLIGENCE
       -> AGENT_RUNNING <-> VALIDATING
       -> ACCEPTED -> DELIVERING -> SUCCEEDED

Any stage -> FAILED_INFRASTRUCTURE | FAILED_VALIDATION | CANCELLED
```

`INTELLIGENCE` may emit `SKIPPED` and continue. `AGENT_RUNNING` may resume after
a Stop Hook denial. `ACCEPTED` requires a complete PASS report. Conversation
`finished` never implies `ACCEPTED`. M2 stops at an accepted/failed result;
delivery states are reserved but not implemented until M4.

Every transition appends a product event in the same transaction as the task
status update. Native OpenHands events retain their native ids and are linked,
not rewritten as the product source of truth.

## Example contracts

The examples define the M2 design target, not a final public API freeze.

### Task request

```json
{
  "contractVersion": "1",
  "idempotencyKey": "repo-123-cve-batch-20261016",
  "repository": {
    "url": "https://github.com/AILearner365/maven-multimodule-app.git",
    "baseRef": "refs/heads/main-runrunning",
    "expectedCommit": "<full-sha>"
  },
  "objective": "Resolve the identified HIGH/CRITICAL OSS dependency vulnerabilities.",
  "constraints": {
    "javaVersionUnchanged": true,
    "springBoot": {"allowPatch": true, "allowMinor": true, "allowMajor": false, "allowDowngrade": false},
    "prohibitSuppressions": true,
    "prohibitedNewSeverities": ["CRITICAL", "HIGH"]
  },
  "acceptance": {
    "buildCommands": ["mvn clean verify"],
    "severityScope": ["CRITICAL", "HIGH"]
  },
  "agent": {
    "profile": "gate2-dependency-remediation-v1",
    "modelProfile": "vertex-gemini-2-5-flash",
    "maxIterations": 250,
    "maxValidationDenials": 3
  },
  "intelligence": {
    "sbri": {"mode": "auto"}
  },
  "delivery": {"mode": "none"},
  "metadata": {"source": "rest"}
}
```

Raw credentials, arbitrary shell environment and delivery tokens are not task
fields. The server resolves named, approved profiles.

### Task status

```json
{
  "taskId": "01JAG8M8R2Y7M5WQ6GQXQ9N7R3",
  "contractVersion": "1",
  "status": "AGENT_RUNNING",
  "stage": "agent",
  "createdAt": "2026-10-16T14:00:00Z",
  "updatedAt": "2026-10-16T14:14:03Z",
  "repository": {"baselineCommit": "<full-sha>", "taskBranch": "openhands/task-01JAG8M8R2Y7M5WQ6GQXQ9N7R3"},
  "openhands": {"conversationId": "<uuid>", "executionStatus": "running"},
  "validation": {"attempts": 1, "accepted": false},
  "links": {"events": "/v1/tasks/01JAG8M8R2Y7M5WQ6GQXQ9N7R3/events", "artifacts": "/v1/tasks/01JAG8M8R2Y7M5WQ6GQXQ9N7R3/artifacts"}
}
```

### Product event

```json
{
  "eventId": "01JAG9A4M8K7V3R5ZGX2P4E6T1",
  "taskId": "01JAG8M8R2Y7M5WQ6GQXQ9N7R3",
  "sequence": 42,
  "timestamp": "2026-10-16T14:14:03Z",
  "type": "validation.completed",
  "stage": "validation",
  "data": {"attempt": 1, "passed": false, "reportArtifactId": "validation-attempt-1"},
  "openhandsEventId": "<native-hook-event-id>"
}
```

Events contain bounded metadata and artifact references, not raw secrets,
reasoning or duplicated full tool payloads.

### Final result

```json
{
  "taskId": "01JAG8M8R2Y7M5WQ6GQXQ9N7R3",
  "outcome": "ACCEPTED",
  "baselineCommit": "<full-sha>",
  "validatedTree": "<git-tree-sha>",
  "validation": {"passed": true, "attempt": 2, "reportArtifactId": "validation-attempt-2"},
  "changes": {"diffArtifactId": "final-diff", "changedFiles": ["pom.xml"]},
  "openhands": {"conversationId": "<uuid>", "finalResponseAvailable": true},
  "delivery": {"status": "NOT_REQUESTED", "pullRequestUrl": null},
  "artifacts": [{"id": "baseline", "sha256": "<sha256>"}, {"id": "final-diff", "sha256": "<sha256>"}]
}
```

## Persistence choice for M2

Start with SQLite for task/event/artifact metadata behind a small store
interface, because this repository already uses local Python and offline tests.
Use append-only sequenced task events and immutable artifact metadata. Store
large logs/reports outside rows under a configured artifact root, with hashes
and relative paths. Put both database and artifact root on durable volumes.

This interface is justified by the immediate server/restart use case; it is not
a generic storage framework. A later production database/object-store adapter
can preserve the contract. Native Agent Server conversation storage remains
separate and must also be durable.

## Incremental migration

### Change 1 — contracts, durable task/event store and read-only API

- Likely files: new `openhands_shared/contracts.py`, `store.py`, `api.py` and
  focused unit/integration tests.
- Move/reuse: encode the approved lifecycle vocabulary, identifiers,
  idempotency key, artifact references and acceptance/result distinction.
- Unchanged: every `scripts/openhands/*` file; all execution behavior.
- Offline tests: JSON round trips, invalid contract rejection, idempotent submit,
  atomic status/event sequence, restart/reopen, status/events/result HTTP tests,
  secret-field rejection.
- Acceptance: two identical submissions produce one task; state/events survive
  process restart; `finished` cannot serialize as accepted without validation.
- Rollback: delete the new package/database; frozen scripts are untouched.

This is the recommended first M2 implementation change.

### Change 2 — deterministic preparation adapter

- Likely files: `preparation.py`, tests with local bare Git fixtures.
- Move/reuse: origin/ref validation, fetch, exact commit pin, unique branch and
  Git worktree creation from `openhands-gate2-execute.sh`.
- Unchanged: current shell preparation and task naming.
- Offline tests: exact SHA, moved branch, dirty/colliding workspace, wrong
  origin, retry after recorded success, concurrent task isolation.
- Acceptance: a prepared task records immutable baseline SHA and unique
  workspace; retry never resets or overwrites an unknown state.
- Rollback: disable worker invocation and remove generated test workspaces.

### Change 3 — baseline adapter and durable artifacts

Implemented on `openhands-service-integration`; operational details and offline
evidence are recorded in
[OPENHANDS-SHARED-BASELINE.md](OPENHANDS-SHARED-BASELINE.md).

- Likely files: `baseline.py`, artifact helper in `store.py`, deterministic
  fixture tests.
- Move/reuse: `MavenService`, scanner, constraints, execution budget and
  baseline serialization from `openhands-gate2-baseline.py`.
- Unchanged: baseline script and its JSON shape for the experiment.
- Offline tests: fake scanner/process fixtures, build failure, incomplete scan,
  no findings, hash/manifest persistence and restart readback.
- Acceptance: BASELINING is fail-closed and its immutable report/artifact hashes
  are addressable through the task API.
- Rollback: task service stops after PREPARING; experiment uses old baseline.

### Change 4 — optional SBRI adapter

Implemented on `openhands-service-integration`; operational details and offline
evidence are recorded in
[OPENHANDS-SHARED-INTELLIGENCE.md](OPENHANDS-SHARED-INTELLIGENCE.md).

- Likely files: `intelligence.py`; existing `sbri_integration.py` receives only
  narrowly necessary extraction after parity tests; tests reuse existing SBRI
  fixtures.
- Move/reuse: applicability, release selection, fingerprinted reuse, bounded
  summary and source-unchanged assertion.
- Unchanged: SBRI CLI, experiment flags, agent wording and cached evidence.
- Offline tests: disabled/not applicable, invalid selection, complete/partial
  result, duplicate avoidance, changed fingerprint and source mutation failure.
- Acceptance: non-applicable tasks skip deterministically; invalid user input
  fails before agent; operational partial evidence remains non-prescriptive.
- Rollback: configure SBRI disabled; baseline and agent stages remain valid.

### Change 5 — native Agent Server adapter

Implemented on `openhands-service-integration` as a non-running native
conversation boundary. Operational details and pinned-version findings are in
[OPENHANDS-SHARED-AGENT-SERVER.md](OPENHANDS-SHARED-AGENT-SERVER.md).

- Likely files: `openhands_runtime.py`, locked deployment manifest/image,
  fake-Agent-Server integration tests.
- Move/reuse: default-agent/profile construction, current Skills/guidance,
  terminal environment, hook config, model and bounds.
- Unchanged: current local SDK runner and live execution command.
- Offline tests: request mapping, native conversation id persistence, event
  linking, server failure/retry reconciliation, restart/rehydration, no delivery
  credentials in agent environment. Use a deterministic fake LLM/server path;
  no Vertex call.
- Acceptance: API-created task reaches one native conversation visible through
  Agent Server; REST and worker observe the same id/status/events.
- Rollback: feature flag worker execution off; retain stored tasks for diagnosis.

Actual Change 5 stops before execution: the pinned `1.50.0` creation path runs
any supplied `initial_message`, so the adapter creates an idle deterministic-id
conversation without one and attaches context separately with `run=false`.
There is no execution feature flag or `/run` call to accidentally enable.
SQLite stores the native association and bounded event references; Agent Server
continues to own full conversation persistence and streaming. Change 6 remains
the required gate for shared validator/Stop Hook parity and agent execution.

### Change 6 — validation/Stop Hook parity

- Likely files: `validation.py`, packaged hook command, validator adapter tests.
- Move/reuse: `DeterministicValidator`, attempt snapshots, concise feedback,
  infrastructure-failure and denial-bound semantics.
- Unchanged: shell hook/validator used by frozen experiment.
- Offline tests: PASS, remediation FAIL/DENY/resume, infrastructure failure,
  bounded termination without acceptance, report corruption, validated-tree
  capture and event ordering.
- Acceptance: only complete PASS enters ACCEPTED; validation feedback is visible
  in the same native conversation; restart does not lose attempt count.
- Rollback: disable shared execution; no effect on frozen experiment.

### Change 7 — UI and thin experiment client parity (M3)

- Likely files: a task-specific Canvas App only if the pinned/supported Canvas
  extension contract passes a spike; otherwise an external minimal page; a new
  thin experiment client script and comparison tests.
- Move/reuse: no lifecycle logic. UI/client only submit, stream/query and export.
- Unchanged: original experiment remains available and authoritative comparator.
- Offline tests: equivalent request from REST/UI/client, consistent status/event/
  result schemas, Canvas deep link, evidence export and source labels.
- Acceptance: all three entry points invoke one stored task and one backend
  lifecycle; native Canvas monitors the same OpenHands conversation.
- Rollback: remove UI/client entry points; API/backend remain usable.

Do not implement the replacement experiment client during M1 or M2.

### Change 8 — validation-gated delivery and server hardening (M4)

- Likely files: `delivery.py`, GitHub adapter, deployment configuration and
  isolation/restart tests.
- Move/reuse: existing deterministic Git auth/PR utilities only after reviewing
  their contracts; baseline-relative diff and validation report.
- Unchanged: agent cannot access delivery credentials; no auto-merge.
- Offline tests: PASS gate, tree changed after validation, idempotent commit/push/
  PR reuse, credential redaction, crash between each side effect, duplicate
  request, branch collision and authorization failure.
- Acceptance: delivery occurs only for the exact validated tree; retries never
  duplicate commits/PRs; PR metadata survives restart.
- Rollback: set delivery mode `none`; accepted results/artifacts remain intact.

## Cross-cutting offline acceptance suite

- Contract/schema compatibility and redaction tests.
- Local Git fixture tests for exact-ref isolation and no destructive recovery.
- Deterministic baseline/SBRI/validator fixtures with no provider calls.
- Fake Agent Server tests for REST/WebSocket event flow and resume.
- Crash/restart tests at every stage boundary.
- Two concurrent tasks against separate workspaces and state/artifact roots.
- `git diff --check`, Markdown link checks and the existing focused OpenHands,
  SBRI, validator, environment and evidence-export tests.

## Decisions and blockers

No decision blocks Change 1. Before native execution work, the team must choose
the target server deployment identity/storage and approve a fully locked
OpenHands image. Before M3 UI submission, verify whether the deployed Canvas
version supports the task-specific App/page contract; monitoring through the
native conversation is independently feasible. Before M4, define GitHub App or
equivalent delivery credentials and repository authorization outside the agent
runtime.

M1 makes no recommendation to upgrade OpenHands. Upgrade evaluation is a
separate compatibility task because the current Canvas patches, serialized
conversation/event schemas and provider dependency set are version-sensitive.
