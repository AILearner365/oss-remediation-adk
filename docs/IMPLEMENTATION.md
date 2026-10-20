# Autonomous OSS Vulnerability Remediation — local SDK implementation

## Correction from a8ba73c6

Removed native_remediation/sandbox.py and its Docker-policy tests; both remain
recoverable in Git history. Removed sandbox.image task configuration, image
preflight, container mounts/cleanup, custom terminal shell_path, forced network=none,
and container-path baseline instructions. No replacement infrastructure or runner.

native.open_conversation uses LocalWorkspace(state/workspace), native TerminalTool
with terminal_type=subprocess, TaskTrackerTool, data-only CycleEvidenceTool,
ValidateRemediationTool and SbriIntelligenceTool. SDK 1.55.1 owns initialization, lazy tools/hooks, reasoning,
persistence/resume and events. No model call occurs in construction. Persisted
state is not silently replaced or migrated from old Docker-mode configuration.

validation.evaluate reuses files.command for local Maven/OSV argv execution
rather than Docker. Existing process timeout/evidence handling remains, and proxy
environment settings are retained. LocalWorkspace.execute_command and actual
native execute_tool(TerminalAction) were also verified with harmless fixtures.
No SDK facilities were monkey-patched in production.

Preparation ordering, identity-bound COMPLETE receipts, recovery checks, task/
policy and journal semantics, independent validator, native Stop feedback, exact
Git exports and GitHub delivery contract are retained. State/evidence/credentials
are outside the repository; no acceptance/delivery tool is exposed to the agent.

## Exact remaining unsupported guarantee

**Live path BLOCKED, not fully completed.** LocalWorkspace/TerminalTool execute
as the host user; so does repository Maven code. They can access sibling private
state, HOME and delivery credentials, load code from the repository and leave
background processes. Instructions, cwd, private file modes and filtered environment
variables do not enforce independent authority against that user. There is no
claim of production-grade security isolation or reliable process quiescence.

files.require_independent_authority explicitly blocks normal runtime.dispatch,
default real validation.evaluate and delivery.deliver. It has no bypass option.
Safe fixtures mock this application guard only to test otherwise retained contracts;
they do not prove it can be removed. Actual SDK construction and harmless fixture
tool invocations remain possible without paid inference or Docker.

This blocker is the mandatory inability of agent/build code to modify trusted
preparation/acceptance records or access delivery credentials. It is not an inability
to use SDK lifecycle APIs, a remote-server problem, or a missing Docker image.
No additional architecture/infrastructure was designed to conceal the limitation.

## Native versus application responsibility map

| Responsibility | Native SDK | Application / actual verification |
| --- | --- | --- |
| Conversation/history/agent loop | Conversation, stable UUID, persistence_dir, agent=None resume | native.open_conversation; real idle construction/restoration, no inference |
| Agent commands | LocalWorkspace + native persistent TerminalTool | Real safe workspace command and persistent shell execute_tool probes; ordinary network/proxies permitted |
| Preparation/baseline gate | Standard explicit caller ordering before send_message/run | runtime.prepare_task/require_preparation; actual idle SDK + fixture baseline; failures/tampering/stale/coverage block |
| Goal-driven reasoning/cycles | One Agent, task_tracker, AgentContext Skills | Stable general context + decision/Maven Skills; optional concise journal records; quality not live-proven |
| Self-check / SBRI | Native ToolDefinition/execute_tool | capabilities.py reuses validator/CLI, separate evidence/budgets, no acceptance authority |
| Independent completion | Native HookConfig.stop command/denial | runtime.hook; real adapter denies missing preparation; controlled PASS/FAIL/INCONCLUSIVE checks |
| Acceptance | Hook invokes deterministic Python checks | Existing Maven/OSV/policy/coverage/immutable-tree code; real build blocked by missing independent authority |
| Delivery policy | Stop PASS precedes accepted completion | Default report_only; explicit draft_pr authorization plus identity/digest/base/tree/create-only/idempotency guards; real delivery blocked |
| Recovery | Native events/state/stats | Minimal task/evidence/run/attempt/delivery claims + locks retained, no history mirror |
| Trust isolation | NOT provided by LocalWorkspace | Outside-workspace records are organizational only; live guard fails closed |

## Installed API authority and tests

Confirmed installed SDK/tools 1.55.1, not assumed upstream main:
- LocalWorkspace(working_dir=...) and execute_command(command, cwd=None, timeout=30.0)
  in sdk/workspace/local.py:17–74.
- TerminalTool.create supports terminal_type, shell_path=None and persistent
  native terminal executors; no custom shell is configured.
- LocalConversation constructor supports persistence_dir, conversation_id,
  hook_config and max_iteration_per_run. Same UUID/directory restores saved native
  agent and history; execute_tool runs a safe tool without inference.

Official sources:
[local workspace](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/workspace/local.py),
[native terminal](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-tools/openhands/tools/terminal/README.md),
[standalone examples](https://github.com/OpenHands/software-agent-sdk/tree/main/examples/01_standalone_sdk).
Installed source and real no-model tests determine version compatibility.

Focused verification: 41 tests pass in installed SDK Python; 33 product/local/parity
tests pass with stdlib Python. Covers actual local command/terminal persistence,
SDK idle persistence/restore, Docker-free fixture preparation, durable gate/failure/
resume checks, native Stop denial, cycle evidence, controlled Maven/OSV outputs,
safe executable stand-ins, proxy propagation, exact-tree delivery/reconciliation,
and real live-path refusal before build/model/delivery. The SDK command helper
emits non-fatal ResourceWarnings; vendor code was not changed.

Mocks/fixtures are explicitly not live proof. No Gemini, real Maven/OSV analysis,
target modification, new PR or remote-server probe ran. Historical PR #214 and
earlier evidence remain intact. Persistent ADC, local-claim durability and Canvas
rendering remain unverified deployment limits, in addition to the security blocker.

## Behavioral alignment with the POC

See [parity and source evidence](POC-PARITY.md) and [configuration](CONFIGURATION.md).
guidance.load uses the installed SDK load_skills_from_dir; AgentContext selects
the decision/Maven pair and disables ambient discovery. The real SDK renderer
delivers both bodies for the initial task and advertises native Skill discovery.
guidance.json hashes sources and rendered context, explicitly NOT model use.
Selected Skills must match on resume; changed configuration is rejected, not migrated.

capabilities.self_validate uses validation.evaluate/compare with the pinned task,
baseline and actual candidate export. It retains separate self-validation UUID
records and cannot write Stop acceptance or spend its attempts. SBRI calls the
existing evaluate CLI with validated versions OR ranges and scopes, bounded
claims/fingerprints and reuse; no SBRI engine is duplicated. The executable is
currently absent, so live intelligence is unavailable. Missing/partial assessments
are not clean findings. SBRI ranks never select a remediation strategy.

journal keeps optional concise decision/outcome records and readable legacy
records. They express rationale/uncertainty, not a model reasoning transcript or
acceptance. Automatic evidence.capture runs at preparation and pre/post-run even
without agent reports: native event count/digest/location and stats, environment
capabilities/proxy-presence only, Git tree/diff/status, artifact references. Native
events remain the sole action/observation history; no duplicate logger/watchers.
COMPLETE binds any pre-edit SBRI result too; interruption cannot silently skip it.

runtime.complete separates VALIDATED/report_only from confirmed DELIVERED and
BOUNDED_FAILURE. delivery.deliver independently rejects missing explicit draft_pr
authorization. Original validation/delivery safeguards remain; no live guard was
removed. Tests cover actual SDK tool dispatch with mocked capability results,
not live Maven/OSV/SBRI execution or Gemini compliance.
