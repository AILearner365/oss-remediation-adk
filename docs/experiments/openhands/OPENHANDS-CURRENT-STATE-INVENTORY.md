# OpenHands shared execution M1 — current-state inventory

Status: M1 read-only code inventory. Date: 2026-10-16.

This document inventories the implementation frozen at
`openhands-gate2-frozen-20261016` (`e5d160cb6080e5c6ed8fef16ca4ba42ab6106c8f`).
It applies the boundary and acceptance criteria in
[OPENHANDS-SHARED-EXECUTION-MIGRATION.md](OPENHANDS-SHARED-EXECUTION-MIGRATION.md);
it does not redefine them. No execution script was changed in M1.

## Current end-to-end path

```text
openhands-gate2-fresh-run.sh
  -> Cloud Shell prepare
  -> live Vertex/OpenHands verification
  -> task branch + Git worktree
  -> deterministic Maven/OSV baseline
  -> optional SBRI pre-edit evidence
  -> local OpenHands SDK Conversation
  -> native Stop Hook -> independent validator -> recovery or termination
  -> local logs/state + sanitized trajectory
  -> commit/push experiment evidence to the control repository
```

The current flow is a proven experiment harness, not a reusable service. Its
stage ordering is useful, but task identity, state locations, environment,
repository identity, task text and publication behavior are embedded in shell
and Python entry points.

## Responsibility inventory

| Responsibility | Current implementation | Inputs | Outputs and side effects | M2 boundary | Reuse and compatibility constraints |
| --- | --- | --- | --- | --- | --- |
| Orchestrate a run | `scripts/openhands/openhands-gate2-fresh-run.sh`; `publish_evidence`, `next_task_id`, main body | optional numeric task id, environment, SBRI CLI arguments | creates timestamped log/evidence directories; invokes three stages; traps exit; may commit and push evidence | Experiment-specific client/exporter | Preserve this command and behavior until parity. Do not move automatic evidence commits into the shared lifecycle. Numeric task ids are experiment labels, not durable service ids. |
| Cloud Shell startup | `openhands-cloudshell-startup.sh` -> `openhands-cloudshell-poc.sh prepare`; functions `check_versions`, `ensure_canvas_installed`, `prepare_runtime`, `patch_vertex_extra`, `patch_vertex_readiness` | Node/npm/uv/gcloud/tmux, Canvas `1.24.0`, Agent Server `1.50.0`, Cloud Shell filesystem | installs an ephemeral global npm package; changes gcloud project when needed; creates `/tmp` cache and tmux paths; patches installed Canvas files; refreshes ADC | Experiment/deployment bootstrap only | Must not enter server business logic. The guarded patches and version refusal remain unchanged pending a separately tested replacement. |
| Environment resolution | `openhands-cloudshell-env.sh`; `openhands_resolve_vertex_env`, `openhands_sync_gcloud_project`, `openhands_verify_vertex_adc` | `VERTEXAI_PROJECT`, `GOOGLE_CLOUD_PROJECT`, gcloud config, defaults | exports `VERTEXAI_PROJECT`, `VERTEXAI_LOCATION`, `UV_CACHE_DIR`; may change active gcloud project; launches pinned ADC preflight | Provider configuration adapter; gcloud mutation remains Cloud Shell-specific | Preserve precedence and explicit project/location. A server deployment must receive config explicitly and must not use the hard-coded POC fallback or mutate gcloud configuration. |
| Environment verification | `openhands-cloudshell-verify.sh` -> `openhands-cloudshell-poc.sh verify`; `verify_all`, `verify_tmux`, `verify_vertex` | prepared Canvas, ADC, Vertex environment | verifies patches/tmux; forces ADC refresh; makes three live Gemini calls | Deployment health checks, with live model checks opt-in | Current verification is live and is prohibited for M1. Offline readiness and live-provider readiness must remain distinct. |
| Refreshable ADC guard | `vertex-adc-preflight.py`; `verify_adc` | expected project, Google ADC | two refreshes, metadata-only JSON/console result; fails before task state creation | Reusable provider preflight, injected/configured by deployment | Never persist tokens. Immediate refresh does not prove long-run renewal. Cloud Shell metadata behavior is not a server credential architecture. |
| Repository fetch and task isolation | `openhands-gate2-execute.sh` lines 50-100 | source checkout, expected GitHub origin, base branch, task id | fetches base; creates/reuses remote task branch only at base SHA; adds Git worktree; creates state directory | Shared preparation component | Preserve exact-base pinning, origin validation, clean isolation and fail-closed collision handling. Generalize repository/ref safely; do not let OpenHands choose the baseline. Current code creates a remote branch before validation. |
| Baseline build and scan | `openhands-gate2-baseline.sh` -> `openhands-gate2-baseline.py`; `verify_target`, `make_workspace`, `main` | worktree, base/task branch, OSV Scanner `2.6.0` path | verifies clean exact baseline; runs `mvn clean verify`; runs complete HIGH/CRITICAL OSV scan; captures constraints; writes `baseline.json`; temporary detailed workspace is deleted | Shared deterministic baseline | Reuse `MavenService`, `create_scanner`, `ConstraintEvaluator`, `ProcessRunner`, `RunWorkspace`, `TraceStore`. Baseline must be durable enough to reproduce validation; current temporary detailed evidence is a gap. |
| SBRI applicability and candidate selection | `sbri_integration.py`; `applicability`, `run_pre_edit_intelligence`, `require_valid_selection` | task text, repository, optional releases/range/config/scanner | writes fingerprinted SBRI execution, result/report/evidence and `latest.json`; may populate Maven caches; must leave source unchanged | Optional shared pre-agent intelligence | Reuse applicability, deterministic selection, fingerprint/cache and bounded summary. Invalid user selection stops before the model; operational SBRI failure does not prescribe a strategy. SBRI stays optional and Maven/Spring-specific. |
| SBRI prompt injection | `openhands-gate2-stop-hook-run.py` lines 550-574; `agent_message` | SBRI record | appends bounded `<SBRI_PRE_EDIT_EVIDENCE>` to task before first action | Shared OpenHands launch adapter | Preserve “security evidence, not upgrade instruction,” full-artifact references, and independent-validation authority. |
| Agent construction | `openhands-gate2-stop-hook-run.py`; `build_agent`, `configure_scanner_terminal` | `LLM`, guidance flags, skills directory, launcher directory, validator/scanner environment | builds native default agent; may load local Skills and guidance; writes executable launchers; changes terminal tool environment | Shared OpenHands adapter, parameterized by task profile | Continue to use `get_default_agent`; do not build a second harness. Preserve one-choice guidance experiments and do not expose delivery credentials. Host paths and `~/.m2` assumptions must be replaced by workspace/deployment configuration. |
| Skills and engineering guidance | `scripts/openhands/skills/*/SKILL.md`, `guidance/*.md`, `project-context/AGENTS.md`; `load_skills_from_dir`, `AgentContext` | task/profile switches | native system suffix and/or progressive-disclosure Skills | Shared task-profile configuration; experiment selects treatment | Preserve file contents and hashes for comparability. Availability/delivery is recorded separately from observed use. Project context is repository-specific. |
| OpenHands autonomous execution | `openhands-gate2-stop-hook-run.py` lines 439-590; `LLM`, `Conversation`, `conversation.send_message`, `conversation.run` | model `vertex_ai/gemini-2.5-flash`, agent, local worktree, prompt, hook, iteration bound | modifies target repository; emits events; persists conversation under state directory; may make network calls and Git commits through terminal | Native OpenHands Agent Server execution plane | Pin SDK/tools together. Preserve native agent/tools/condenser/stuck detection. The local SDK conversation is not registered with Agent Server or Agent Canvas and cannot be assumed visible in the UI. |
| Independent completion validation | `openhands-gate2-stop-hook.sh` -> `openhands-gate2-validate.sh` -> `openhands-gate2-validate.py`; `DeterministicValidator.validate` | saved baseline, current worktree, scanner, constraint policy | Maven build/test/startup, fresh OSV scan, original-finding comparison, new-finding and policy checks; writes `validation.json` and attempt snapshots | Shared deterministic validation | Reuse validator and report. Keep it independent of model judgment. The host-Python isolation in `openhands-gate2-validate.sh` is a required current workaround until dependencies are packaged into the worker image. |
| Stop Hook recovery | runner `build_hook_config`; SDK `HookConfig`; `openhands-gate2-stop-hook.sh` | validator result, attempt counter, max denials | native Stop Hook ALLOW/DENY; concise failure evidence returns to same conversation; snapshots every attempt; bounded termination can occur without acceptance | Native hook mechanism plus repository-owned validator command | Preserve `termination != acceptance`, infrastructure-failure distinction, three-denial experimental default and report-backed feedback. Server hook command must run where validator/workspace are accessible. |
| Conversation/event capture | `Conversation(... persistence_dir=..., delete_on_close=False)` and native SDK event log | conversation events | `base_state.json` and per-event JSON under `state/conversation/<id>` | Native OpenHands persistence, supplemented by product task/event state | Retain native event ids/order and conversation id. Configure durable storage for restart recovery. Do not make product acceptance depend only on an in-memory callback. |
| Sanitized trajectory export | `export-event-history.py`; `scrub`, `project` | persisted event JSON | new `events.jsonl` and hash manifest; omits reasoning/private fields and redacts common secrets | Experiment-specific evidence exporter; reusable sanitization policy | Unknown event payloads remain omitted. Export is explicitly not a universal secret-safety guarantee and requires review before publication. |
| Evidence summary | `openhands-gate2-evidence-summary.py`; `main` | copied validation attempts/final result | human-readable validation progression | Experiment/reporting | It summarizes but never changes acceptance. |
| Experiment evidence publication | `publish_evidence` in `openhands-gate2-fresh-run.sh` | run logs, task state, Git worktree | copies bounded artifacts/diff/metadata; commits and pushes only the evidence directory on `openhands-poc-evaluation` when configured | Experiment-specific | Preserve for the future thin experiment client. Shared backend publishes artifact references/state, not control-repository evidence commits. |
| Target delivery | No deterministic PR delivery exists in Gate 2. The task branch is created remotely before execution, and agent terminal access may commit/push; evidence publication is a different repository operation. | target Git credentials available to host/agent environment | at most a target branch; no validation-gated idempotent PR contract | Future shared delivery component (M4) | Do not claim PR support. Delivery credentials must be unavailable to the agent. Recheck validated tree hash before commit/push/PR; never auto-merge. |

## Reusable product components already present

- Deterministic execution: `ExecutionBudget`, `ProcessRunner`, `MavenService`,
  scanner factories, `ConstraintEvaluator` and `DeterministicValidator`.
- Workspace/evidence primitives: `RunWorkspace` and `TraceStore`.
- SBRI: applicability, release selection, source fingerprinting, cache/reuse,
  bounded agent context and bounded review export.
- OpenHands configuration: default-agent construction, native Skills,
  task/context guidance, terminal launchers and native Stop Hooks.
- Evidence hygiene: per-attempt validation snapshots, observable-only trajectory
  projection, hash manifest and baseline-relative Git diff.

These are reusable implementations, not yet stable service APIs. M2 should
extract narrow call boundaries around them rather than copy their logic.

## Current data and lifecycle constraints

- State is spread across a target Git checkout, `~/.openhands/gate2`,
  `~/.openhands/gate2/run-logs` and committed experiment evidence.
- A shell-generated numeric task id is collision avoidance, not idempotency.
- The baseline SHA is authoritative and validation compares the final checkout
  with that recorded baseline even if the agent made intermediate commits.
- A completed OpenHands conversation is not a successful task. Only the last
  complete independent validation report can establish PASS.
- An unreadable/missing validation report is infrastructure failure, not a
  remediation failure and never PASS.
- No current component atomically links product task status, OpenHands
  conversation status, validation attempts, artifacts and delivery metadata.
- Current Git branch creation and evidence push use ambient host credentials;
  delivery credential separation is not implemented.

## Existing-document classification

The labels below are for migration use only. Nothing is deleted or rewritten.

### Current authority or current experiment operation

- `OPENHANDS-SHARED-EXECUTION-MIGRATION.md`: approved migration authority.
- `GATE2-ORCHESTRATED-RUNBOOK.md`: current frozen experiment operation.
- `GATE2-TASK.md`: current frozen task/policy input.
- `ENGINEERING-EVALUATION-SCORECARD.md`: adopted evaluation contract.
- `SBRI-INTEGRATION.md`: current implementation description, but its branch
  status sentence needs verification now that the code is in the frozen tip.
- `SBRI-INTEGRATION-EVALUATION-20261016.md`: latest SBRI integration evidence.

### Historical evidence

- `GATE2-NATIVE-REMEDIATION.md`, `GATE2-TRAJECTORY-ANALYSIS.md`,
  `STOP-HOOK-POC.md`, `GATE2-STOP-HOOK-EXPERIMENT.md` and all
  `GATE2-STOP-HOOK-TASK*-ANALYSIS.md` files.
- `GATE2-PRE-TASK04-EVIDENCE-GAPS.md`,
  `GATE2-SCANNER-INTERFACE-CROSS-RUN-REVIEW.md`,
  `GATE2-TASK15-TASK16-STABILITY-COMPARISON.md`,
  `GATE2-TASK17-*`, `GATE2-CROSS-RUN-ENGINEERING-EVALUATION-20261011.md`
  and `TASK14-HARNESS-REVIEW.md`.
- `MAVEN-DEPENDENCY-RESEARCH-TEST.md` and
  `VERTEX-AUTH-HISTORICAL-REGRESSION.md`.

### Potentially stale or needing verification before operational reuse

- `OPENHANDS-VERTEX-POC.md`: valuable patch/auth evidence, but the installed
  package patch is tied to Canvas `1.24.0` and Agent Server `1.50.0`.
- `TASK07-CONFIGURATION-AND-LIVE-RUN.md`,
  `TASK07-RUNTIME-STRATEGY-AUDIT.md`, `TASK08-INSTRUCTION-TRACEABILITY.md`,
  `STALE-KNOWLEDGE-STRATEGY-RESEARCH.md` and
  `ENGINEERING-RELIABILITY-REMEDIATION-DRAFT.md`: investigation or proposed
  treatments, not shared-backend requirements.
- `OPENHANDS-CRITIC-FEASIBILITY.md`: version-specific feasibility evidence;
  no Critic is part of the approved shared lifecycle.
- Natural ADC renewal after nominal expiry remains unverified; immediate
  preflight success must not be promoted to long-running reliability.

## M1 conclusion

The migration should retain the deterministic product controls and evidence
semantics, replace shell-global identity/state with a durable task record, and
move OpenHands execution to its native Agent Server. The frozen orchestrator
remains the behavioral comparator throughout the migration.
