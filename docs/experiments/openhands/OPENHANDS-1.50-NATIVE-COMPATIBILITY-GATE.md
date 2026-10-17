# OpenHands 1.50.0 native compatibility gate

Status: **PASSED for the scoped M2 native compatibility gate**. Date: 2026-10-17.

This is the focused M2 acceptance gate for the shared backend. It exercised the
actual OpenHands Agent Server, SDK and tools at `1.50.0` in disposable local
state. It did not use Gemini, Vertex AI or another external model; touch a real
target repository; run Maven, OSV or remediation; push a target branch; or
create a pull request. No upstream OpenHands source was patched.

The native conversation and command Stop Hook protocols work in the tested
runtime, including DENY continuation. Source tracing proved the fresh
`hook_config: null` response is lazy native initialization, not response-model
loss: a non-running context message installs and persists the effective hook.
The adapter now performs a two-phase identity check and requires an immediate
post-initialization GET to expose the exact effective hook. The actual pinned
runtime rerun passed without a restart, external model or execution dispatch.

## Reproducible runtime

The environment was created outside the repository with Python 3.12.3:

```text
uv venv --python 3.12 /tmp/<gate>/venv
uv pip install --python /tmp/<gate>/venv/bin/python \
  openhands-agent-server==1.50.0 openhands-sdk==1.50.0 openhands-tools==1.50.0
uv pip freeze --python /tmp/<gate>/venv/bin/python
```

Selected resolved versions were:

```text
openhands-agent-server==1.50.0
openhands-sdk==1.50.0
openhands-tools==1.50.0
agent-client-protocol==0.12.1
fastapi==0.143.3
starlette==1.8.0
uvicorn==0.54.0
pydantic==2.14.1
litellm==1.105.1
openai==2.54.0
```

The complete 194-package `uv pip freeze` output had SHA-256
`9a78c3b0bdce17c6799aff3cddebcd716f879897c2529a53d99a7e66118d323b`.
The three OpenHands distributions are exact pins, but their dependency
metadata does not fully pin the transitive graph. A deployable image therefore
needs the complete reviewed lock, not only the three top-level requirements.

`GET /server_info` reported Agent Server, SDK and tools `1.50.0`, Python
3.12.3, and local conversation runtime. The server listened only on loopback,
used disposable state/workspace directories, disabled telemetry export and
VS Code, and ran with an allowlisted minimal environment containing no cloud
credentials. The existing host OpenHands installation was not changed.

## Verification matrix

| Item | Verdict | Actual pinned-runtime evidence |
| --- | --- | --- |
| Exact Agent Server/SDK/tools versions | PROVEN | `/server_info` returned `1.50.0` for all three distributions. |
| Deterministic conversation ID and idle creation | PROVEN | A caller-supplied UUID was returned unchanged with status `idle`. |
| Context event with `run=false` | PROVEN | Event returned successfully and conversation remained `idle`; the local provider received no request. |
| Lookup and event search | PROVEN | Conversation lookup and paginated native event search returned the created records. |
| Native persistence across restart | PROVEN | The same UUID, events, workspace and hook configuration reloaded from disposable native state. |
| Native idempotent UUID reuse | PROVEN | Fresh provision, immediate retry and post-restart retry reused one UUID, context event and SQLite association. |
| Command Stop Hook transport | PROVEN | Actual native `/run` executions used a loopback-only deterministic provider and exercised all five hook fixtures below. |
| Shared adapter conversation mapping | PROVEN | Actual adapter provisioned the deterministic UUID after effective-hook verification and persisted it in SQLite. |
| Profile/workspace/guidance/Skills serialization | PROVEN | Two-phase checks verified profile revision, model, worktree, guidance, Skill, terminal environment, tags and hook. |
| Intended prepared worktree | PROVEN | Native conversation used the exact disposable prepared `LocalWorkspace` and stayed idle during provisioning. |
| Native event links without payload copying | PROVEN | Actual context event identity was linked in SQLite; content remained in native storage. |
| Product retry/reconciliation without duplicate run | PROVEN | Same-process and post-restart retries reused one conversation/context; adapter issued zero `/run` calls. |
| Native finish cannot imply acceptance | PROVEN | Native fixtures reached `finished`; no durable validation PASS or accepted product result was created. The failed adapter task remained `NOT_STARTED`. |
| Credential isolation | PROVEN | Server and local provider ran with a minimal environment and no external provider credentials; conversation profile used no secret refs. |
| Worker ownership/network-loss reconciliation | PARTIAL | Zero dispatch during provision/recovery was proven; ambiguous real `/run` response remains covered only offline. |
| Hook access to validator state/artifacts | NOT PROVEN | Synthetic hook fixtures were used; Maven/scanner validation was intentionally prohibited. |
| Canvas 1.24.0 end-to-end compatibility | NOT PROVEN | Canvas was not installed or exercised in this gate. Prior source inspection is not runtime proof. |

`PROVEN` means exercised through these actual pinned distributions. `PARTIAL`
means a native portion was exercised but a material product path remained
blocked. `NOT PROVEN` does not inherit a success verdict from mocks or source
inspection.

## Native conversation and context behavior

Creation with no `initial_message` produced the requested deterministic UUID
and stayed idle. Posting the task context to
`/api/conversations/{id}/events` with `run=false` also stayed idle and made no
provider request. Lookup and event search worked. After Agent Server restart,
the same durable conversation reappeared with its prior event sequence and
configuration.

The server was only allowed to call `/run` for the Stop Hook transport matrix.
Its sole model profile targeted a loopback OpenAI-compatible fixture with a
disposable key. The fixture deterministically selected the native finish tool;
all nine requests were recorded at that loopback listener. No external LLM
endpoint or credential was configured.

## Actual command Stop Hook protocol

The native hook command ran with its current working directory equal to the
conversation workspace. It received these non-secret environment values:
`OPENHANDS_PROJECT_DIR`, `OPENHANDS_SESSION_ID`, and
`OPENHANDS_EVENT_TYPE=Stop`. Its stdin shape was:

```json
{
  "event_type": "Stop",
  "message": null,
  "metadata": {"reason": "agent_finished"},
  "session_id": "<conversation UUID>",
  "tool_input": null,
  "tool_name": null,
  "tool_response": null,
  "working_dir": "/tmp/<gate>/workspace"
}
```

Observed behavior:

| Fixture | Exit/output | Native result |
| --- | --- | --- |
| ALLOW | exit 0, `{"decision":"allow"}` | `success=true`, `blocked=false`, conversation finished. |
| DENY once | exit 2 with reason and `additionalContext` | `success=false`, `blocked=true`; same conversation called the local fixture again with `[Stop hook feedback]` and the exact additional context, then ALLOWed. |
| Command failure | exit 1 | `success=false`, `blocked=false`; conversation still finished. |
| Malformed output | exit 0, non-JSON stdout | `success=true`, `blocked=false`; conversation still finished. |
| Timeout | exceeded one second | exit -1 with timeout error, `success=false`, `blocked=false`; conversation still finished. |

The actual `HookExecutionEvent` exposed `kind`, source/id/timestamp/parent,
`hook_event_type`, `hook_command`, `hook_input`, `success`, `blocked`,
`exit_code`, stdout/stderr and, when applicable, reason,
`additional_context` and error. Null optional fields may be omitted by JSON
serialization.

This confirms native fail-open behavior for command failure, malformed
successful output and timeout. Native termination is not product acceptance.
The existing shared rule—accept only a complete durable independent PASS—must
remain authoritative. Direct invocation of the product hook CLI is covered by
the offline validation suite and is not counted as native transport evidence.

## Root cause and correction

The original run exposed `hook_config: null` on creation and immediate warm
GET, although the hook later executed and appeared after cold reload. Pinned
source tracing established the complete path:

1. `StartConversationRequest` validates the hook and
   `ConversationService._start_conversation` copies it into
   `StoredConversation`.
2. `EventService` constructs `LocalConversation(...,
   hook_config=self.stored.hook_config)`.
3. `LocalConversation.__init__` assigns it to `_pending_hook_config`; fresh
   `ConversationState.hook_config` remains null.
4. `_compose_conversation_info` serializes that state unchanged, so creation
   and immediate warm GET both accurately report null.
5. `send_message` calls `_ensure_agent_ready` for the OpenHands agent. Lazy
   plugin/Skill initialization merges hooks, assigns the effective result to
   state, constructs the hook processor and persists the state.
6. The subsequent GET and cold reload expose the installed configuration.

This is initialization timing and a pending-versus-effective runtime
representation, not a different response model or serialization omission.
HTTP 201, the UUID and persisted request metadata remain insufficient proof.

The correction first verifies every observable identity field while allowing
only the exact pending representation (`hook_config is null`). It submits the
uniquely marked context with `run=false`, observes that event, performs an
immediate GET, and requires exact equality with the complete approved hook.
Missing, partial, modified or still-null hooks fail closed. No delay, restart,
request echo, upstream patch or model call is used.

The actual rerun observed `null -> configured`, completed as
`CONTEXT_ATTACHED`, linked one event, remained native `idle`, left execution
`NOT_STARTED` and acceptance false, and issued zero `/run` calls. Same-process
retry and a server/database restart reused the same UUID and context. A native
conversation whose command was deliberately changed was rejected with
`CONVERSATION_IDENTITY_MISMATCH` and `RECOVERY_REQUIRED`.

`recover_provisioning(task_id)` is a trusted explicit recovery operation for
that single pre-execution failure code. It reconstructs the original durable
identity, never creates a second conversation, searches for the context marker
before sending, never resends an uncertain event, never calls `/run`, and
requires the full effective hook. It appends `agent.recovery.completed` without
erasing the earlier recovery event. An actual controlled recovery ended
`CONTEXT_ATTACHED`, idle and unaccepted with one linked event.

## Persistence, restart and remaining concerns

Native conversations/events and product SQLite records have separate durable
stores and must be backed up and reconciled together by stable UUID. This test
proved native cold reload and successful product reconciliation. The following
remain unresolved:

- exercise ownership and restart around an uncertain real `/run` response
  without risking a duplicate model execution;
- exercise the real product validator and artifact availability in the hook
  runtime in an explicitly authorized environment;
- build from a full dependency lock and immutable image;
- test the deployed Canvas 1.24.0 build against the same backend; and
- perform a separately authorized live remediation after all no-model gates
  pass.

The blocking M2 native-compatibility condition is resolved, so M3 may begin as
its own bounded change. This does **not** make the shared backend production
ready: delivery and live remediation remain disabled until the remaining
runtime, deployment, Canvas and separately authorized live-validation gates
are met.
