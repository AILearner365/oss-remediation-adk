# OpenHands shared native Agent Server adapter — M2 Change 5

Status: implemented non-running native conversation integration. Date: 2026-10-16.

This change connects the shared task lifecycle to the native OpenHands Agent
Server while preserving the Change 6 validation boundary. It provisions one
native conversation and attaches the verified task context, but it cannot run
the agent. It does not call a model, Maven, a scanner, SBRI, GitHub or delivery.

## Pinned API evidence

The implementation was checked against the published `1.50.0` wheels for
`openhands-agent-server`, `openhands-sdk` and `openhands-tools`, not current-main
documentation. It uses only:

- `GET /server_info` for the exact server/SDK/tools version gate;
- `GET /api/conversations/{id}?include_skills=true` for reconciliation and
  effective profile verification;
- `POST /api/conversations?include_skills=true` for native conversation
  creation;
- `POST /api/conversations/{id}/events` with `run=false` for task context; and
- `GET /api/conversations/{id}/events/search` for native event references.

Pinned `1.50.0` has an important creation-path behavior: when
`initial_message` is present, `ConversationService._start_conversation` sends it
with `run=True`, regardless of the nested `SendMessageRequest.run` value. The
shared adapter therefore omits `initial_message`, disables auto-title, creates
an idle conversation, and sends context through the event endpoint with
`run=false`. It never calls `/run`.

## Trusted internal invocation

There is no new public execution route. A trusted worker calls the adapter only
after preparation, baseline and intelligence have durably completed:

```python
from pathlib import Path

from openhands_shared import (
    HttpAgentServerTransport,
    OpenHandsAgentProfile,
    OpenHandsRuntimeConfig,
    SharedOpenHandsRuntime,
)

profile = OpenHandsAgentProfile(
    profile_id="gate2-dependency-remediation-v1",
    model_profile_id="vertex-gemini-2-5-flash",
    native_agent_profile_id="<deployment-owned UUID>",
    native_agent_profile_revision=7,
    native_model="vertex_ai/gemini-2.5-flash",
    required_skills=(
        "dependency-remediation-decision",
        "maven-dependency-evidence",
    ),
    allowed_terminal_environment=(
        "PATH",
        "OPENHANDS_OSV_EXECUTABLE",
        "OPENHANDS_OSV_MAVEN_REGISTRY",
    ),
    guidance_files=(
        Path("/srv/control/scripts/openhands/guidance/general-engineering.md"),
        Path("/srv/control/scripts/openhands/project-context/AGENTS.md"),
    ),
    stop_hook_argv=(
        "/opt/openhands-shared/bin/stop-hook",
        "--task-id", "{task_id}",
        "--workspace", "{workspace}",
    ),
)
runtime = SharedOpenHandsRuntime(
    store,
    OpenHandsRuntimeConfig(
        artifact_root=Path("/durable/openhands-artifacts"),
        agent_server_identity="primary-agent-server",
        profiles=(profile,),
    ),
    HttpAgentServerTransport(
        "http://agent-server:8000",
        # Deployment authentication, if any, is supplied only by the transport.
        headers_factory=deployment_auth_headers,
    ),
).provision(task_id)
```

`POST /v1/tasks` remains registration-only and cannot call this operation.

## Task, workspace and profile mapping

Provisioning requires product status `AGENT_RUNNING` and execution status
`NOT_STARTED`. It verifies the registered request against immutable preparation,
successful baseline and continuing intelligence records, then verifies all
required artifact sizes and SHA-256 hashes.

The prepared task worktree is passed directly as native `LocalWorkspace` with
`worktree=false`; Agent Server does not create another clone or worktree. The
common Git directory, task branch and baseline ancestry must still match.
Before Change 5 provisioning, `HEAD` must still equal the baseline and the tree
must be clean. The verifier has a distinct post-launch identity mode that keeps
the common-repository/branch/baseline-ancestry checks while permitting agent
edits and descendant commits; Change 6 must use that mode only after it has
durably recorded execution start.

The deployment maps the product agent/model pair to a native Agent Profile UUID
and exact revision. The adapter verifies the returned profile snapshot, native
model, required Skills, appended guidance, terminal tool and terminal
environment allowlist. The native profile must use `secret_refs=[]`. Request
payloads contain no `secrets`, arbitrary environment or delivery credentials;
transport authentication never enters the conversation request.

The initial user event contains the registered objective, constraints,
acceptance requirements, exact repository/baseline identity and verified SBRI
summary. Disabled/not-applicable SBRI is explicit and does not claim evidence.
Applicable summaries retain `<SBRI_PRE_EDIT_EVIDENCE>` and these boundaries:

- candidate selection limits collected evidence, not available strategies;
- a security rank is not an implementation decision;
- residual candidate findings are not acceptable final results; and
- independent deterministic validation remains authoritative.

SBRI is never rerun by this adapter.

## Stop Hook and validation boundary

The request attaches a native `HookConfig.stop` command from deployment-owned
configuration. Placeholder success commands are rejected and the effective
command hash is part of the profile fingerprint. Change 5 proved native request
wiring only. Change 6 now supplies the shared validator, denial/resume policy,
execution ownership and controlled `/run` boundary described in
[OPENHANDS-SHARED-VALIDATION.md](OPENHANDS-SHARED-VALIDATION.md).

Change 5 itself exposes no execution-start operation. Conversation
creation and context attachment leave both native execution and product
execution `NOT_STARTED`. A native status other than `idle` is an identity/
recovery error. Native `finished` never changes validation to `PASSED`, never
sets `accepted=true`, and never transitions the task to `ACCEPTED` or
`SUCCEEDED`.

## Persistence and safe reconciliation

SQLite schema version 5 adds:

- `openhands_runtimes`: immutable task/conversation/server/profile/model/
  workspace/baseline/fingerprint identity plus mutable bounded lifecycle,
  last-event and recovery metadata; and
- `openhands_event_links`: append-only native event id, kind, timestamp and
  observed order linked to a product event sequence.

Full native conversations and event payloads remain in Agent Server persistence.
SQLite stores no reasoning, tool payload, model content or secret-bearing native
event body.

The conversation UUID is deterministically derived from the deployment server
identity and durable task id, and is supplied through native
`StartConversationRequest.conversation_id`. Native `1.50.0` returns the existing
conversation for that UUID. A crash after native creation but before SQLite
commit therefore reconciles by UUID and verifies workspace, tags, profile,
model, Skills, guidance and hook configuration before binding it. It never
blindly creates a second conversation.

The task-context event carries a unique task/request marker. Retry searches the
native event store before sending. If message submission is uncertain and the
marker cannot be observed, the runtime enters `RECOVERY_REQUIRED`; automatic
resend is disabled. Conflicting deterministic conversation identity also
requires operator recovery.

## Agent Canvas 1.24.0 compatibility

Source inspection at tag `v1.24.0` (`7dc6805406ea3c76cb4a3ce407c3c72d481b0ac6`)
confirms Canvas uses the native Agent Server conversation list, event API and
event WebSocket, with route `/conversations/:conversationId`. When Canvas is
connected to the same Agent Server backend, the monitoring path is therefore:

```text
<canvas-origin>/conversations/<native-conversation-id>
```

The product task stores that exact native UUID. No Canvas code was modified.
Canvas must have the same backend selected; the route alone does not encode a
backend identity. Change 5 does not prove a deployed browser/Canvas session,
Vertex keyless readiness, cross-origin routing or a complete UI workflow.

## Offline verification and remaining blockers

The in-process fake-server suite covers pinned request shape, contract mapping,
SBRI outcomes, workspace/profile/Skill/guidance/hook verification, deterministic
conversation recovery, response loss before SQLite commit, message uncertainty,
event ordering, payload non-copying, database restart/migration, credential
isolation, missing/incompatible servers, dirty post-agent workspaces and the
unvalidated-completion boundary. Existing shared-backend and Gate-2 regression
tests remain unchanged except later schema-version expectations advancing to 6.

The subsequent actual pinned-runtime gate is recorded in
[OPENHANDS-1.50-NATIVE-COMPATIBILITY-GATE.md](OPENHANDS-1.50-NATIVE-COMPATIBILITY-GATE.md).
It proved the native no-model conversation and command-hook transport, but also
found that a fresh `1.50.0` conversation response omits `hook_config` until a
server restart. The shared adapter correctly fails closed because it cannot
verify the installed validation command. M3 and operational execution remain
blocked pending a narrow safety-preserving resolution and gate rerun.
