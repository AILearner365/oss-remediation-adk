# OpenHands shared validation and Stop Hook — M2 Change 6

Status: implemented offline foundation. Date: 2026-10-17.

This change integrates the existing independent `DeterministicValidator` with
the native OpenHands Agent Server 1.50.0 Stop Hook and adds a controlled native
execution-start boundary. It does not add delivery, UI work, a second agent
loop, live provider testing, or public execution endpoints. Task registration
remains non-executing.

## Reused validation authority

`ExistingDeterministicValidationRunner` constructs the same
`RemediationRequest`, `RunWorkspace`, `ProcessRunner`, approved OSV scanner,
`ConstraintEvaluator`, and `DeterministicValidator` used by the frozen Gate-2
validator. It reconstructs the immutable `RepositoryBaseline` from the Change
3 report and validates the current prepared worktree. It does not rerun
baseline or SBRI.

Before validation it verifies the registered repository, prepared common Git
directory, task branch, baseline ancestry, native conversation, execution
claim, and hashes of the baseline and intelligence artifacts. Legitimate agent
edits and descendant commits are allowed; a foreign repository, branch, or
history fails closed.

Every attempt retains a canonical report envelope and SHA-256. The envelope
includes the complete existing validator report, original-finding coverage,
new-finding and constraint results, failure classification, hook decision, and
exact Git state. The latter is captured with a temporary `GIT_INDEX_FILE`:

```text
validated HEAD + git write-tree of tracked/untracked working state
               + SHA-256 of baseline/HEAD/tree/porcelain status
```

The temporary index does not stage changes in the agent worktree. Later
delivery must recapture all three values and reject any drift.

## Pinned native Stop Hook protocol

Pinned OpenHands 1.50.0 source establishes this command-hook contract:

- Agent Server executes the Stop Hook command in the conversation workspace
  and writes hook event JSON to stdin.
- Exit `0` with `{"decision":"allow"}` permits completion.
- Exit `2` or `{"decision":"deny"}` blocks completion.
- `additionalContext` from a DENY returns to the same conversation.

The deployment-owned executable invokes `python -m openhands_shared.stop_hook`
(or an equivalent locked entry point) with a
deployment-owned configuration file, durable task id, and exact workspace. The
configuration names approved Maven/scanner profiles and paths; it contains no
credentials. The native request still contains the rendered absolute hook
command and no secret or arbitrary environment payload. Controlled start also
checks the executable's deployment-approved SHA-256 and verifies that the
configuration's database, artifact root, profile and build commands match the
running task service.

The profile command shape is:

```python
stop_hook_argv=(
    "/opt/openhands-shared/bin/stop-hook",
    "--config", "/etc/openhands-shared/validation.json",
    "--task-id", "{task_id}",
    "--workspace", "{workspace}",
)
stop_hook_sha256="<approved executable SHA-256>"
```

The executable calls `SharedValidationService.handle_stop(task_id,
workspace_argument=workspace)`. OpenHands owns invocation and continuation;
the product adapter owns the deterministic verdict and attempt policy.

| Independent result | Native decision | Product result |
| --- | --- | --- |
| Complete PASS | ALLOW | `ACCEPTED`; delivery remains `NOT_REQUESTED` |
| Remediation failure within denial bound | DENY with bounded actionable evidence | same conversation resumes; task returns to `AGENT_RUNNING` |
| Remediation failure after denial bound | ALLOW only to terminate | `FAILED_VALIDATION`, never accepted |
| Scanner/infrastructure failure | ALLOW only to terminate | `FAILED_INFRASTRUCTURE`, never accepted |
| Missing/corrupt/invalid report | ALLOW only to terminate | validator/infrastructure failure, never accepted |

The native SDK falls open for command transport errors other than exit `2`.
The command boundary therefore emits explicit non-acceptance termination text,
and product acceptance still requires a complete durable PASS. A native
`finished` state without PASS is reconciled to `FAILED_VALIDATION`.

## Controlled execution start

There is no public start endpoint. A trusted worker calls:

```python
runtime.provision(task_id)
runtime.start_execution(task_id, worker_id="worker_01")
```

Immediately before `POST /api/conversations/{conversation_id}/run`, the adapter
re-verifies the pinned server/profile/model/Skills/guidance, exact context
event, clean baseline workspace, complete stage artifacts, and installed
executable Stop Hook command. SQLite then atomically records one worker owner,
claim token, and `INTENT_RECORDED` event before the external call.

An existing intent is never dispatched again. Retry observes native state: a
running/finished conversation confirms dispatch; idle, unavailable, or
ambiguous state becomes `RECOVERY_REQUIRED`. Response loss after the server
accepted `/run` reconciles to `DISPATCHED` without a second call. Competing
worker ids are rejected.

`reconcile_execution(task_id)` maps native terminal state without inferring
acceptance. Native completion creates the immutable accepted result only when a
durable PASS attempt exists. The result records the validation artifact and
validated tree; delivery stays `NOT_REQUESTED`.

## Persistence and restart behavior

SQLite schema version 6 migrates in place and adds:

- `execution_claims`: immutable task/conversation/worker/claim identity plus
  monotonic intent, dispatch, or recovery state; and
- `validation_attempts`: durable sequence, outcome/classification, report
  artifact/hash, coverage, hook decision/feedback, exact Git state, native
  conversation and optional HookExecutionEvent association.

Attempt reservation and `VALIDATING` transition are atomic. Final artifact
metadata, attempt verdict, status/acceptance, and sequenced completion event
commit together. An immutable report written before SQLite commit is reconciled
without rerunning the validator. A restarted `RUNNING` attempt with no complete
report becomes validator failure and is not rerun automatically. No retry
resets agent edits, discards attempt history, or issues another model run.

## Frozen parity and explicit differences

The frozen scripts are unchanged. Shared Change 6 preserves independent
validator authority, original/new finding comparison, constraint checks,
bounded DENY feedback, same-conversation continuation, and the rule that bound
termination is not acceptance.

The shared path adds durable transactionality, failure classification, exact
Git tree identity, multi-process dispatch ownership, and restart
reconciliation. The frozen shell hook records infrastructure failure in a file
and ALLOWs termination; the shared path also ALLOWs termination but atomically
marks the product task `FAILED_INFRASTRUCTURE`. Neither path calls that PASS.

## Offline verification and remaining gaps

Fake Agent Server/validator and local Git tests cover execution gates,
PASS/ALLOW, repeated DENY, denial exhaustion, infrastructure/corrupt reports,
tree drift, crashes around report/SQLite persistence, uncertain `/run`, worker
competition, native event association, restart, API compatibility, credential
isolation, and no live network/model/Maven/scanner use.

Pinned 1.50.0 source was inspected for `/run`, command-hook exit codes, JSON
fields, HookExecutionEvent, and same-conversation feedback. The pinned packages
are not installed in the offline test environment, so an actual no-model Agent
Server command-hook transport test remains required before deployment. Live
Vertex/Gemini, Maven, OSV, denial/resume, and long-running restart compatibility
remain deliberately unverified and disabled.
