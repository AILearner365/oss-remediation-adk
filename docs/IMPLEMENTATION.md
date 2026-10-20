# Autonomous OSS Vulnerability Remediation — standalone SDK implementation

## Actual responsibility map

| Responsibility | Native SDK | Application code / verification |
| --- | --- | --- |
| Lifecycle, history, recovery | Conversation, LocalWorkspace, persistence_dir, stable conversation_id | native.open_conversation; actual SDK idle creation/restoration test, no inference |
| Preparation before inference | Supported explicit caller sequence before send_message/run | runtime.prepare_task/require_preparation; deterministic repo/validator reuse, durable COMPLETE receipt; ordering/failure tests |
| Autonomous investigation/reassessment | One native Agent, LLM, TerminalTool, TaskTrackerTool | native.INSTRUCTIONS; journal intent/outcome via small SDK CycleEvidenceTool; reasoning quality not live-proven |
| Trust domains | LocalWorkspace is NOT a sandbox | sandbox.py launches restricted short-lived containers for native terminal/builds; launch/mount/quiescence tests only, real image boundary not exercised |
| Completion interception | Native HookConfig.stop command and deny feedback | runtime.hook, CLI exception-to-deny; actual native Stop denial test |
| Acceptance | Native invokes hook, not model self-report | validation.evaluate/compare; exact Git export, Maven/OSV/policy/coverage checks reused; controlled process-output tests |
| Draft delivery | Invoked only by trusted acceptance | delivery.deliver; exact evidence/tree/base checks, create-only push and draft reconciliation; local Git and remote doubles |
| Durable task/side-effect safeguards | SDK persists events/status/stats | task/baseline/receipt/journal/attempt/run/delivery records and locks retained; no history mirror, service or custom agent loop |

## Implemented changes

Removed the remote HTTP Native transport, request-config serialization, separate
attach/reconcile-attachment stage, session-key CLI arguments and remote /run
coordination. ADC preflight now uses current SDK runtime/environment instead of
searching an Agent Server process. No Agent Server extension or SDK patch.

Normal start creates the SDK conversation idle, performs deterministic preparation
and baseline, stores COMPLETE bound to conversation/task/repository/base/tree/digest,
rechecks preparation, sends the objective and calls conversation.run(). Optional
prepare is diagnostic, not a mandatory external normal stage. Run/resume recheck
durable evidence/deadline/base before any inference; missing native persistence is
not silently replaced. SDK persistence/resume is official, not another state system:
the same ID/directory restore the persisted agent with agent=None, then the
application verifies task-pinned model/context/tool configuration before execution.

The old external orchestration prohibition concerned the remote direction. The
current explicit caller sequence is authorized by the standalone SDK direction.
The [remote blocker](NATIVE-PREPARATION-BLOCKER.md) is historical, not a conclusion
that the local SDK calling pattern cannot implement the requested gate.

The host SDK control directory is separate from repository files. This matters:
SDK 1.55.1 lazily discovers ambient project plugins. Never make the untrusted repo
the host LocalWorkspace. Operator home/plugins remain trusted deployment inputs.
Only native terminal has arbitrary commands; its configured shell_path enters a
container with explicit mounts, read-only root/Git metadata/baseline, dropped caps,
no-new-privileges, bounded resources and no network/home/credentials/socket.
The native file-editor is not exposed because it edits the host filesystem.
Ordinary terminal tools handle repository editing; no bespoke command tools added.
CycleEvidenceTool is necessary structured agent evidence without access to trusted
state; it cannot accept candidates or deliver. Host TaskTracker has a fixed SDK
persistence destination that the repository cannot symlink or modify.

Build/scanner commands also execute in containers, not merely with stripped env.
Fresh exact source/build-cache mounts and explicit read-only scanner input mounts
exclude trusted acceptance/preparation/claims. Effective POM is raw output under
exported source/target; host parsing and decisions remain outside writable mounts.
Agent descendants are stopped before candidate capture. Denial feedback tells the
agent to reset its native terminal to start another sandbox, preserving one agent.

## Installed API authority

Checked installed SDK/tools 1.55.1:
- sdk/conversation/conversation.py: factory forwards LocalWorkspace, persistence_dir,
  conversation_id, hook_config and max_iteration_per_run to LocalConversation.
- sdk/conversation/impl/local_conversation.py:211 constructor; 1551 lazy initialization;
  1928 run; 3142 execute_tool (caller-owned safety, bypasses confirmation checks).
- sdk/conversation/state.py:470–594 native create/restore and automatic persistence.
- sdk/workspace/local.py:17–74 host filesystem/execute_command, not isolation.
- tools/terminal/definition.py:294–340 documented terminal_type/shell_path params;
  tools/terminal/terminal/subprocess_terminal.py launches that shell with -i.
- tools/task_tracker/definition.py: fixed state persistence; sdk/hooks command Stop.

Official references:
[SDK](https://docs.openhands.dev/sdk),
[standalone hello world](https://docs.openhands.dev/sdk/guides/hello-world),
[persistence](https://docs.openhands.dev/sdk/guides/convo-persistence),
[pre-run execute_tool example](https://github.com/OpenHands/software-agent-sdk/blob/main/examples/01_standalone_sdk/30_tom_agent.py),
[upstream LocalConversation](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py).
Upstream main/docs can differ; installed APIs and focused tests decide compatibility.
execute_tool is available but not needed to run trusted deterministic Python
preparation, so no artificial preparation tool was introduced.

## Verification and proof limits

Focused suite: 31 tests pass in installed SDK Python; 26 product/sandbox tests
also pass with stdlib-only Python. Product/scanner/Git/delivery
tests use temporary local fixtures and explicit native/GitHub/Maven/OSV doubles.
Real native tests create/restore a persisted idle conversation with an inference
tripwire, initialize the actual adapter hook (denying missing preparation), and
execute the cycle-evidence tool through supported local execute_tool without
inference. They also check native Stop command denial/configuration. Sandbox tests
inspect launch arguments, generated symlink rejection and failure semantics, not
a real image or attack test. Generated special files are rejected before host parsing.
The historical remote probes were not rerun.

**Not live-proven:** standalone Gemini, Maven/OSV baseline/candidate inside these
containers, full objective remediation, reassessment quality, draft delivery of
this product implementation, secure deployment/container behavior, persistent ADC,
production claim durability, Canvas/browser rendering. The prior native one-file
smoke/PR #214 at f72e5308704960ee911f382f96bf0b7948435216 remains separate evidence.

**Current genuine deployment blocker:** no approved local sandbox/toolchain image.
Network is deliberately disabled; arbitrary Maven downloads/current online OSV/
research cannot work until offline inputs are provisioned or a separately reviewed
credential-safe egress policy is implemented. No host/network fallback is present.
This is not a remote API limitation and does not block implementing/testing the
local SDK lifecycle. No live run, target edit, paid inference or PR was performed.

[Operations](OPERATIONS.md) describes actual commands and [contract](../PRODUCT-CONTRACT.md)
states invariants. Next step is no-model verification of an approved immutable
image/toolchain/isolation boundary, not a Gemini remediation run.
