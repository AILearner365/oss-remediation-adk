# OpenHands shared execution M1 — native integration feasibility

Status: M1 source and documentation investigation. Date: 2026-10-16.

This assessment supports the direction in
[OPENHANDS-SHARED-EXECUTION-MIGRATION.md](OPENHANDS-SHARED-EXECUTION-MIGRATION.md).
It does not authorize an SDK upgrade, a Canvas fork or a live model run.

## Evidence and version boundary

The Gate-2 execution command directly pins:

```text
openhands-sdk[vertex]==1.50.0
openhands-tools==1.50.0
```

The Cloud Shell UI bootstrap separately pins Agent Canvas `1.24.0` and
`OH_AGENT_SERVER_VERSION=1.50.0`. M1 resolved the published Python packages in
an isolated `uv` environment without making an LLM call and inspected their
source, models and signatures. With explicit constraints, Agent Server, SDK and
tools resolve together at `1.50.0`. Installing `openhands-agent-server==1.50.0`
alone resolved a newer SDK (`1.55.1`) because its dependency is not an exact
lock; a deployable build therefore must pin and lock the whole set.

Primary upstream evidence:

- [OpenHands SDK/Agent Server repository and ownership boundaries](https://github.com/OpenHands/software-agent-sdk)
- [Agent Server architecture and deployment guide](https://github.com/OpenHands/docs/blob/main/sdk/arch/agent-server.mdx)
- [Agent Canvas architecture](https://github.com/OpenHands/docs/blob/main/openhands/usage/agent-canvas/overview.mdx)
- [v1.50.0 release](https://github.com/OpenHands/software-agent-sdk/releases/tag/v1.50.0)
- [v1.50.0 local conversation](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py)
- [v1.50.0 hook processor](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-sdk/openhands/sdk/hooks/conversation_hooks.py)
- [v1.50.0 Agent Server conversation routes](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-agent-server/openhands/agent_server/conversation_router.py)
- [v1.50.0 event routes](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-agent-server/openhands/agent_server/event_router.py)

Current upstream documentation is useful for the intended architecture, but
only pinned `1.50.0` package/source inspection is used below to assert the
available runtime contract.

## Capability findings

| Capability | Pinned 1.50.0 finding | Supported integration point | Limit or repository responsibility |
| --- | --- | --- | --- |
| Backend/server execution | Supported. `openhands-agent-server` is a FastAPI service around native conversations and tools. | Run the native Agent Server; use its Python remote conversation or REST client. | It executes conversations; it is not the OSS-remediation baseline/SBRI/validation/delivery orchestrator. |
| Native UI | Supported through Agent Canvas connected to Agent Server. Canvas owns conversations, events, files, terminal and model/profile UX. | Point Canvas at the same Agent Server used by shared tasks; return the conversation id/deep link. | A local SDK `Conversation` created by the current runner is not registered with Agent Server and will not automatically appear in Canvas. Structured remediation submission is not a stock conversation form. |
| REST API | Supported. The server exposes OpenAPI plus `/api/conversations`, per-conversation events, run/pause/interrupt, final response, files, Git views, skills/settings and health endpoints. | Prefer generated/native client contracts. Create conversation with agent/workspace/hook, send initial message, run, query state/events. | Product endpoints still need `POST /tasks`, task status/events/result and idempotency. Do not duplicate native conversation endpoints. |
| Live event streaming | Supported through the Agent Server WebSocket event socket; SDK conversations also accept callbacks. | Canvas and API clients subscribe to the native event stream. Product worker records references/projections into task events. | In-memory callbacks are insufficient for durable product state. Streaming deltas and durable events have different retention semantics. |
| Conversation/session management | Supported: create, search, fetch, run, pause, interrupt, fork, resume from persistence, final response and execution status. | Store `conversation_id` on the product task and treat it as the OpenHands execution identity. | OpenHands conversation status is not product acceptance. Task lifecycle needs additional deterministic stages and terminal states. |
| Event/state persistence | Supported. SDK persists base state and per-event JSON when `persistence_dir`/file store is configured; Agent Server catalogs and rehydrates conversations. | Put Agent Server conversation storage on a durable volume and retain native event ids. | Default paths are local filesystem. Secrets require `OH_SECRET_KEY` to remain restorable. Local file locking is not a general distributed database/NFS guarantee. Product task/artifact metadata needs its own durable store. |
| Workspace execution | Supported through `LocalWorkspace` and remote workspace APIs; server can use local or Docker conversation runtime. | Give the native server an isolated prepared workspace or a sandbox runtime. | Canvas itself is not isolation. Production must define container/VM permissions, network, CPU/memory/pids and artifact mounts. |
| Git/worktrees | Supported in Agent Server with `worktree=true`, per-conversation roots and Git diff/commit inspection routes. | Potentially useful after parity tests. | Native start-point selection is not the approved exact-ref/task-branch contract. M2 preparation should continue to pin/fetch/create the product worktree deterministically, then pass it to OpenHands. |
| Skills and repository guidance | Supported through `AgentContext`, `load_skills_from_dir`, server skill APIs and repository context. | Reuse current Skills and guidance in the native agent profile. | The current treatment flags and hash evidence are repository-owned. A Skill being available or injected does not prove use. |
| Custom tools | Supported by native `Tool` definitions, client tools, MCP and plugins. The default tool preset is already used. | Continue with default OpenHands tools and the existing harness-owned terminal launchers. | No new generic tool/plugin framework is justified. Validation and delivery remain outside agent authority. |
| Stop Hooks/equivalent | Supported natively. `HookConfig.stop` executes command hooks; DENY feedback returns to the same conversation and produces `HookExecutionEvent`. | Preserve the current Stop Hook adapter and validator semantics, packaged where the Agent Server can execute it. | OpenHands supplies interception and feedback transport, not the product validator, retry bound or acceptance decision. A hook infrastructure error must remain non-PASS. |
| Concurrent runs | Supported at server level with configurable `max_concurrent_runs`; per-conversation worktrees and Docker runtimes are available. Pinned source also has conversation ownership leases. | Bound worker concurrency and give every task unique workspace/state/artifact paths. | A concurrency limit is not isolation. Maven caches, branch names, scanner resources, credentials and delivery operations still require explicit isolation/locking. Load and crash tests are required. |
| Model/provider configuration | Supported by `LLM`/profiles and server settings. The current runner supplies model and no API key. | Store a provider/profile reference or approved model fields in the task, resolve credentials server-side. | Do not accept arbitrary secrets in the task contract or persist provider tokens in events. Exact package/profile schema is versioned. |
| Vertex AI/Gemini | Supported by the SDK's `vertex` extra through LiteLLM; the repository has successful 1.50.0 evidence with `vertex_ai/gemini-2.5-flash` and ADC. | Install `openhands-sdk[vertex]`; provide project/location and server-side ADC. | Agent Canvas `1.24.0` required two local patches for the server launcher extra and keyless readiness. Long-duration Cloud Shell ADC renewal remains unverified. See the customization audit. |

## Native API surface relevant to the shared flow

Pinned Agent Server source exposes, among others:

```text
POST /api/conversations
GET  /api/conversations/{conversation_id}
POST /api/conversations/{conversation_id}/events
GET  /api/conversations/{conversation_id}/events/search
POST /api/conversations/{conversation_id}/run
POST /api/conversations/{conversation_id}/pause
POST /api/conversations/{conversation_id}/interrupt
GET  /api/conversations/{conversation_id}/agent_final_response
GET  /api/git/changes
GET  /api/git/diff
```

`StartConversationRequest` accepts a local workspace, optional worktree flag,
initial message, max iterations, stuck detection, agent/profile, hook config,
plugins, tags and observability metadata. `SendMessageRequest` accepts role,
text/image content and an optional run flag. These are native conversation
contracts and should not be re-exposed under different repository-owned names.

## UI integration decision

The supported path is:

```text
shared task API -> deterministic PREPARE/BASELINE/SBRI
                -> native Agent Server conversation
                <-> Agent Canvas for native monitoring/intervention
```

Do not try to attach the existing local SDK runner process to Canvas. The task
service should create the native server conversation and persist its id. Canvas
can then use its existing conversation/event/file/terminal views.

Stock Canvas does not model the complete remediation request or the deterministic
pre/post-agent stages. For M3, first prove monitoring by opening the native
conversation. For submission, evaluate a small task-specific Canvas App/page
that calls the shared task REST API and navigates to the resulting conversation.
Canvas Apps are an upstream beta extension point; this is preferable to a UI
fork, but version compatibility and trust/deployment must be proven before it is
committed. A normal external form calling the same REST API remains the fallback.

## Persistence and restart boundary

Use two linked but distinct records:

- Native OpenHands conversation persistence: full agent state and event log,
  addressed through `conversation_id` and rendered by Canvas.
- Product task persistence: task contract, lifecycle stage, baseline and
  validation ids, artifact manifest, delivery gate and `conversation_id`.

On worker restart, the product record tells the worker which deterministic
stage to resume or reconcile; the Agent Server rehydrates the native
conversation. Reconciliation must be idempotent. Re-running an uncertain Git
or delivery side effect is forbidden without inspecting recorded state.

## What OpenHands does not replace

OpenHands does not supply this repository's exact baseline contract, SBRI
policy, original-finding comparison, independent validator, evidence bundle,
validation-gated PR delivery or experiment publication. Those are product
controls. Conversely, this repository must not rebuild agent stepping,
conversation continuation, event streaming, Skills, tool execution, Stop Hook
transport or the Canvas conversation UI.

## Feasibility verdict

Native integration is feasible and should be based on Agent Server, not a
service wrapper around the current local `Conversation`. The main risks are
version lock/reproducibility, durable storage semantics, task/conversation
reconciliation, workspace isolation, Canvas Vertex keyless configuration and
packaging the independent validator beside the native server runtime. All are
testable incrementally without changing the frozen experiment.
