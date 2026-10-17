# OpenHands 1.50.0 native compatibility gate

Status: **FAILED — M3 is blocked**. Date: 2026-10-17.

This is the focused M2 acceptance gate for the shared backend. It exercised the
actual OpenHands Agent Server, SDK and tools at `1.50.0` in disposable local
state. It did not use Gemini, Vertex AI or another external model; touch a real
target repository; run Maven, OSV or remediation; push a target branch; or
create a pull request. No upstream OpenHands source was patched.

The native conversation and command Stop Hook protocols work in the tested
runtime, including DENY continuation. The shared adapter nevertheless cannot
safely provision a newly created conversation: the native creation response
omits `hook_config` until the server is restarted, while the adapter correctly
requires that configuration to be visible before execution can be enabled.
The adapter therefore fails closed. This gate must be rerun after that mismatch
has a narrow, safety-preserving resolution.

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
| Native idempotent UUID reuse | PARTIAL | Pinned source and observed state support existing-conversation reuse; the product adapter is blocked before successful binding. |
| Command Stop Hook transport | PROVEN | Actual native `/run` executions used a loopback-only deterministic provider and exercised all five hook fixtures below. |
| Shared adapter conversation mapping | FAILED | Fresh creation returned `hook_config: null`; adapter rejected the identity, persisted recovery state and did not start execution. |
| Profile/workspace/guidance/Skills serialization | PARTIAL | Native profile, workspace, hook and context were observed independently; the adapter could not complete its full verification/binding path. |
| Intended prepared worktree | PARTIAL | Native execution used the exact disposable `LocalWorkspace`; the blocked adapter path did not run it. |
| Native event links without payload copying | NOT PROVEN | Existing offline tests cover this, but the native adapter never reached binding in this gate. |
| Product retry/reconciliation without duplicate run | PARTIAL | Deterministic native state survived restart and the adapter failed closed; successful product reconciliation was blocked. |
| Native finish cannot imply acceptance | PROVEN | Native fixtures reached `finished`; no durable validation PASS or accepted product result was created. The failed adapter task remained `NOT_STARTED`. |
| Credential isolation | PROVEN | Server and local provider ran with a minimal environment and no external provider credentials; conversation profile used no secret refs. |
| Worker ownership/network-loss reconciliation | NOT PROVEN | Covered only by offline fake-server tests; no ambiguous live dispatch was induced. |
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

## Blocking adapter mismatch

The shared adapter was connected to this real server with a disposable product
task. Native creation used the expected deterministic conversation UUID and
stored the supplied hook. However, the immediate creation/lookup response
exposed `hook_config: null`. The native metadata on disk contained the hook,
and the hook later executed. After server restart, lookup exposed the complete
configuration.

Pinned `1.50.0` returns HTTP 201 for a newly created UUID and HTTP 200 for an
existing UUID, but the current transport deliberately returns only the parsed
object. Accepting a null hook based on HTTP status would not prove that the
required validation command was installed, and would weaken collision and
recovery checks. No such workaround was made.

The adapter raised `RuntimeIdentityError` for the mismatched hook, persisted
`CONVERSATION_IDENTITY_MISMATCH`, set the runtime to `RECOVERY_REQUIRED`, and
left execution `NOT_STARTED` and product acceptance false. This is the correct
safe outcome, but it means actual shared-backend compatibility is **FAILED**.
There were no source-code compatibility changes in this gate.

## Persistence, restart and remaining concerns

Native conversations/events and product SQLite records have separate durable
stores and must be backed up and reconciled together by stable UUID. This test
proved native cold reload and product failure persistence, not successful
end-to-end reconciliation. The following remain unresolved:

- establish a pinned native response or API that exposes the effective hook on
  fresh creation, or add another equally strong pre-run attestation; then rerun
  this entire no-model gate;
- exercise ownership and restart around an uncertain real `/run` response
  without risking a duplicate model execution;
- exercise the real product validator and artifact availability in the hook
  runtime in an explicitly authorized environment;
- build from a full dependency lock and immutable image;
- test the deployed Canvas 1.24.0 build against the same backend; and
- perform a separately authorized live remediation after all no-model gates
  pass.

The shared backend is **not ready for M3**. The recommended next action is a
narrow compatibility investigation/fix for authoritative fresh-conversation
hook verification, backed by an actual `1.50.0` regression fixture, followed
by a rerun of this gate. Do not begin Canvas/client replacement, delivery or a
live remediation on the strength of the native hook result alone.

