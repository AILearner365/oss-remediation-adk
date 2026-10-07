# OpenHands POC handoff

**Branch:** `openhands-poc-evaluation`

**Parent branch:** `context-hygiene-clone-challenge-before-commitment`

## Why this branch exists

Evaluate whether an established coding-agent harness can replace generic harness infrastructure currently implemented around Google ADK.

Do not assume the existing ADK architecture is the target design. Preserve useful principles, but first test what the established harness already provides.

## Experiment progression

**CONTINUE EVALUATION.**

- Task-01: native run and externally prompted recovery; no deterministic completion interception; agent could finish despite validator disagreement.
- Task-02: Stop Hook mechanics and same-conversation continuation PROVEN; validator integration FAILED / INFRASTRUCTURE-CONFOUNDED. **INVALID FOR RECOVERY/CONVERGENCE COMPARISON.** Later manual validation: 18/24 original findings absent, six remained; build/tests and Java/suppression/diff-hygiene policies passed, no new prohibited findings; Boot 4.2.0-M2 failed as `unparseable`; overall FAILED.
- Task-03: first clean-validator Stop Hook run reviewed; **BOUNDED_FAIL**. Three deterministic denials and same-conversation continuation worked. Parent downgrade corrected, but final build failed; empty scan coverage prevents treating reported 24/24 absence as proven remediation. See [Task-03 analysis](../experiments/openhands/GATE2-STOP-HOOK-TASK03-ANALYSIS.md). Task-02 is not a valid convergence comparator.
- Task-04: hardened-evidence clean rerun reviewed; **BOUNDED_FAIL**. Remaining targets improved 22→13 after the first denial, then stayed at 13 through attempts 3 and 4. Final comparison was complete (11 resolved / 13 remaining / 0 unknown), build/tests passed, but 30 new prohibited findings, a Boot 4.0.6→3.3.1 downgrade, and hygiene failure remained. No pager recurrence or new harness capability gap was proven. See [Task-04 analysis](../experiments/openhands/GATE2-STOP-HOOK-TASK04-ANALYSIS.md).
- Post-Task-04 evidence-transport adjustment: the existing Stop Hook now returns decision-critical finding identities and current package versions for remaining targets and new prohibited findings, exact unknown identities when present, Spring Boot baseline/current evidence on policy failure, and diagnostic-artifact paths. It still returns evidence only—not remediation instructions—and preserves the same native OpenHands continuation/bounded-completion design.
- Task-contract tooling adjustment for the next clean run: explicitly expose `~/bin/osv-scanner` to OpenHands as optional investigation/self-validation evidence. OpenHands decides when/how often to use it; the deterministic baseline and independent completion validator continue to use the same OSV Scanner with Maven-aware local repository support and remain authoritative. No scan sequence, dependency version, or remediation recipe is prescribed.
- Task-05: **BOUNDED_FAIL**, reviewed 2026-10-07. First validation proved 2/25 targets resolved with build, scan coverage and Java/Boot policies passing. The first post-feedback divergence was E27: Boot parent 4.0.6→3.2.5 while retaining the Boot 4-family `spring-boot-starter-webmvc`; Central has no 3.2.5 artifact for that coordinate. Attempts 2–4 failed build/scan and Java/Boot configuration checks, with all 25 targets UNKNOWN. Two temporary successful 4.0.6 builds and usable SBOM scans did not prevent renewed downgrade and final 2.7.18. Java FAIL reflects added compiler source/target settings still equal to 21, not a proven numeric Java downgrade. Native Stop Hook continuation/bounds and improved identity/version transport worked; no new required harness or missing-tool gap was proven. Primary observed weakness remains sustained evidence interpretation and engineering reassessment. Exact condensation-caused context loss is unresolved. See [Task-05 analysis](../experiments/openhands/GATE2-STOP-HOOK-TASK05-ANALYSIS.md).
- Task-05 capture retained all 407 observable events and all four validator JSON/log pairs. Existing metadata fix `c67b6e2e` is retained: literal README backticks and shared Vertex resolution in the parent orchestrator. This review adds no further code change relative to remote `85b05b05`. Historical evidence remains unchanged. Condensation payloads and untracked-file bytes are outside the published projection; the hygiene filename heuristic missed the downloaded HTML error-page POM, but build/scan/policy checks prevented acceptance. No validator, runtime, contract, strategy or retry-bound change was made.
- **Next action after Task-05:** do not perform another identical same-model OpenHands Task-06 merely to retry. Proceed to the planned OpenCode comparison under equivalent task, independent validation, bounds and available-model constraints. A stronger-model isolation experiment remains deferred until an approved model is available; availability was not re-probed during review. **CONTINUE EVALUATION**, with no custom planner, memory/reasoning loop, remediation recipe, agent-helping AGENTS.md/Skills or added retries.
- Current operator runbook: [Gate 2 orchestrated runbook](../experiments/openhands/GATE2-ORCHESTRATED-RUNBOOK.md). Use it as the canonical pre-run/execute/failure/evidence workflow for the next clean task.
- Fresh-run automation is now a staged orchestrator rather than mixing preparation and execution in one script. `scripts/openhands/openhands-gate2-fresh-run.sh [task-id]` runs `STARTUP -> VERIFY -> EXECUTE`; the execution stage itself lives in `scripts/openhands/openhands-gate2-execute.sh <task-id>`. Startup prepares/repairs the pinned Cloud Shell OpenHands/Vertex runtime, Verify is non-repairing and proves the prepared runtime (patch presence, ADC, tmux, and a real Vertex/OpenHands Gemini smoke call), and Execute alone owns experiment setup: clean task branch/worktree/state, deterministic baseline, and native Stop-Hook agent run. If no task id is supplied, the orchestrator chooses the next numeric task id after the highest task branch/worktree/state it can see (minimum next id 05); an explicit id such as `05` still overrides that choice. Every orchestrated run writes a persistent local diagnostic bundle under `~/.openhands/gate2/run-logs/run-<UTC timestamp>/` with `startup.log`, `verify.log`, `execute.log`, `combined.log`, `task-id.txt`, and `status.txt`. On exit—success or failure—the orchestrator also copies those logs plus available `baseline.json`, `validation.json`, Stop-Hook diagnostic files, final target Git state/diff, and a sanitized observable OpenHands event trajectory into `docs/experiments/openhands/evidence/gate2-orchestrated-run-<UTC timestamp>/`, commits only that evidence directory, and pushes it to `openhands-poc-evaluation`. The trajectory export preserves observable messages, actions, tool arguments/results, errors, state transitions, and Stop-Hook decisions/feedback in sequence while intentionally excluding internal reasoning/thought fields, opaque provider thought signatures, raw LLM responses, and other unreviewed/private payloads. If automatic push fails, the run result is preserved and the local/repository evidence paths are printed for manual recovery. Set `AUTO_PUSH_EVIDENCE=0` to disable only the automatic commit/push. Shared environment resolution remains in `scripts/openhands/openhands-cloudshell-env.sh`: project precedence is explicit `VERTEXAI_PROJECT`, then `GOOGLE_CLOUD_PROJECT`, then active gcloud project, then the POC fallback `deutschebank-aipocs`; startup synchronizes the active gcloud project when needed and Execute sources the same resolver so the actual agent process receives `VERTEXAI_PROJECT`, `VERTEXAI_LOCATION`, and `UV_CACHE_DIR`.

See [Task-02 evidence review](../experiments/openhands/GATE2-STOP-HOOK-TASK02-INVALID-RUN.md) for source-linked conclusions, attribution limits, and fix history. Earlier setup and research sections below retain historical context.

## Current status

Gate 1 setup is proven and has a repeatable `verify` health check in Google Cloud Shell:

- Agent Canvas 1.24.0
- Agent Server / SDK 1.50.0
- native OpenHands agent
- Vertex AI through ADC
- `vertex_ai/gemini-2.5-flash`
- current company Vertex model availability for this POC: **Gemini 2.5 Flash only**; no stronger Gemini Pro model is presently available for a controlled model-isolation rerun
- no model API key
- successful end-to-end smoke response: `VERTEX_OPENHANDS_OK`

Three environment/integration gaps were observed and have temporary Cloud Shell POC workarounds:

1. Canvas versioned launcher omitted `openhands-sdk[vertex]`.
2. Canvas local keyless readiness did not recognize Vertex ADC.
3. Canvas supplied a `TMUX_TMPDIR` whose directory did not exist.

See `docs/experiments/openhands/OPENHANDS-VERTEX-POC.md` for exact evidence, workaround, production treatment, disk notes, and next gates.

Use `scripts/openhands/openhands-cloudshell-poc.sh` to reproduce/check the current POC setup. The script is version-guarded and must stop rather than guessing if a newer Canvas build no longer matches the known patch points.

## Active problem stack

```text
Parent objective:
  reduce custom coding-agent harness infrastructure
    |
    +-- Gate 1: reproducible OpenHands + Vertex POC
    |     status: manual path proven; repository capture/bootstrap established
    |
    +-- Gate 2: bounded autonomous OSS-remediation capability test
    |     status: task-01 FAILED; task-02 infrastructure-confounded; tasks 03–05 BOUNDED_FAIL; CONTINUE EVALUATION
    |
    +-- Gate 3: company-laptop package/runtime feasibility
          status: wait for Gate 2
```

## Gate 2 completed experiment

Target repository:

```text
AILearner365/maven-multimodule-app
baseline: main-runrunning
disposable branch: openhands-poc-task-01
```

The remote `openhands-poc-task-01` branch was created directly from `main-runrunning`.

Control/evaluation files on this branch:

- `docs/experiments/openhands/GATE2-TASK.md`
- `docs/experiments/openhands/GATE2-NATIVE-REMEDIATION.md`
- `scripts/openhands/openhands-gate2-prepare.sh`
- `scripts/openhands/openhands-gate2-baseline.sh`
- `scripts/openhands/openhands-gate2-baseline.py`

## Gate 2 results and current decision

**CONTINUE EVALUATION — not ADOPT, not REJECT.**

Native run: 24 baseline HIGH/CRITICAL findings; 10 resolved, 14 remained; new prohibited findings introduced; Spring Boot 4.0.6 → 3.2.6 violated the no-downgrade constraint. Build/tests passed; independent validator FAILED. OpenHands declared completion.

One recovery run continued the same conversation with external deterministic failure evidence. The agent corrected the Boot downgrade and introduced-finding regression. Java, suppression policy, build/tests, and delivery-hygiene checks passed. Seven original findings resolved, 17 remained; independent validator FAILED again. OpenHands again declared completion and treated remaining findings as non-actionable without adequate evidence.

The trajectory demonstrates useful investigation, tools, and evidence-driven strategy changes, alongside early constraint loss, repeated failed actions, unsupported release/CVE assumptions, and unjustified completion. Recovery is a meaningful policy correction, not remediation success or an independent replication.

See [Gate 2 trajectory analysis](../experiments/openhands/GATE2-TRAJECTORY-ANALYSIS.md) for separate phase ratings, first divergences, attribution limits, and exact external research questions. The [evidence capture](../experiments/openhands/evidence/gate2-20261004/README.md) preserves 366 sanitized SDK events, full observable messages/actions/observations, baseline and recovery validator snapshots, and source hashes.

Evidence limits: native validator results survive in the recovery user message; a separate native validator snapshot was not recovered. Recovery's delivery-hygiene PASS coexists with a leftover `high_critical_vulnerabilities_current.txt` in its changed-file list. Do not infer complete cleanup from that PASS.

## Research-informed assessment (historical plan; Task-03 now reviewed)

**CONTINUE EVALUATION — not ADOPT, not REJECT.**

External OpenHands review is now recorded in the trajectory analysis. Current OpenHands SDK documentation provides native completion-control patterns (Goal Completion Loop and Stop hooks) aimed at premature completion. The later dummy POC and Task-03 now verify native interception and continuation for the installed stack; they do not establish adequate remediation convergence.

A stronger-model isolation run is currently **blocked/deferred** because the company Vertex environment exposes only `gemini-2.5-flash` for this POC. Keep model quality marked **UNRESOLVED** rather than attributing the Gate 2 failures entirely to OpenHands or entirely to Gemini.

The controlled completion-interception experiment was designed to keep the same model, clean task baseline, task contract, tools, and deterministic validator, and change only **native completion control**. Task-03 implemented that direction: the existing validator denied completion and returned evidence to the same OpenHands conversation for bounded continuation.

Do not add AGENTS.md, remediation Skills, custom retry/planner/memory frameworks, dependency recipes, or additional solution hints as part of this evidence review. Those would add variables without evidence that they address the observed failure.

If native completion control still leaves materially poor evidence interpretation or requires humans to supply engineering strategy rather than validation evidence, stop OpenHands-specific tuning and proceed to the planned OpenCode comparison under the same task/validator/model-availability constraints.

Gate 3 and platform adoption remain pending.

## Stop Hook POC

A minimal native OpenHands Stop Hook proof has been added and **PASSED on 2026-10-04**:

- `scripts/openhands/openhands-stop-hook-poc.py`
- `docs/experiments/openhands/STOP-HOOK-POC.md`

Purpose: prove, on the installed SDK 1.50.0 and existing `vertex_ai/gemini-2.5-flash` path, that the first completion attempt can be deterministically denied, feedback can be injected into the same conversation, execution can resume, and a later completion attempt can be allowed.

This is intentionally isolated from the OSS-remediation task and does not call the Gate 2 validator yet. The first execution exposed a packaging-only prerequisite: `openhands-sdk` does not include the `openhands.tools` default preset, so the POC command must also supply matching `openhands-tools==1.50.0`. The corrected run passed with two Stop-hook invocations: the first was denied, deterministic feedback was observed in the same conversation, the second was allowed, and the conversation finished. Native completion-control wiring is therefore proven for SDK/Tools 1.50.0 with Vertex Gemini 2.5 Flash.

## Gate 2 Stop Hook experiment

The native Stop Hook POC passed. Task-02 subsequently ran with the protocol below; its invalid classification and completed manual validation are recorded above.

Fresh target branch:

```text
AILearner365/maven-multimodule-app
openhands-poc-task-02-stop-hook
```

Control files:

- `scripts/openhands/openhands-gate2-stop-hook.sh`
- `scripts/openhands/openhands-gate2-stop-hook-run.py`
- `docs/experiments/openhands/GATE2-STOP-HOOK-EXPERIMENT.md`

The experiment keeps the Gate 2 task, Gemini 2.5 Flash, native agent, tools, and deterministic validator constant. The only intended behavioral variable is native completion interception: validator PASS allows completion; validator FAIL is returned as evidence to the same conversation.

Default bound: three denied completion attempts. A later forced termination caused only by reaching the experiment bound is reported as `BOUNDED_FAIL`, never as deterministic success.

Use a separate worktree and state directory so task-01 evidence/workspace remain untouched.

### Task-02 first Stop Hook run: infrastructure-confounded

The first real-validator Stop Hook run ended with `STOP_HOOK_INVOCATIONS=4`, `DENIED_COMPLETIONS=3`, and `GATE2_STOP_HOOK_RESULT=BOUNDED_FAIL`, but evidence review shows the deterministic validator never actually executed. Each hook invocation failed during Python imports with `AttributeError: module 'google.genai.types' has no attribute 'TranslationConfig'`.

Cause: the validator child process inherited the OpenHands ephemeral `uv run` Python/package environment and mixed it with the existing system Google ADK installation. No `validation.json` was produced. The hook wrapper incorrectly converted this infrastructure error into a normal validation `DENY`.

Do **not** interpret this run as evidence that three rounds of authoritative validator feedback failed to converge. It is invalid for the remediation comparison. Task-02 persisted events also prove native Stop Hook mechanics and same-conversation continuation.

Completed afterward: manual validation recorded partial remediation but overall FAILED; validator environment isolation was implemented before Task-03. See the Task-02 review for evidence and provenance limits.


## Explicit return point

If Gate 2 is promising, perform the corporate-laptop feasibility test. If that also passes, treat OpenHands as a qualified platform candidate and compare it fairly against OpenCode before committing to a production platform.

Do not turn the Cloud Shell npm bundle patches into production architecture by default.


### Gate 2 Stop Hook validator isolation fixed

The task-02 infrastructure confounder was traced to `openhands-gate2-validate.sh` resolving `python` from the active OpenHands `uv run` environment. That mixed temporary OpenHands packages with the host Google ADK installation and raised `google.genai.types.TranslationConfig` during import.

Fix on `openhands-poc-evaluation`:
- validator wrapper now selects host Python outside `VIRTUAL_ENV`, probes `google.adk`/`pydantic` dependencies, and sanitizes Python environment variables;
- Stop Hook removes stale validation output before each invocation;
- missing fresh validation output is classified as `INFRASTRUCTURE_FAIL`, not deterministic `DENY`;
- outer runner reports infrastructure failure distinctly.

Do not relax the Spring Boot qualifier behavior for this experiment. Existing policy tests deliberately fail closed on qualifier-bearing versions such as RCs; `4.2.0-M2` should therefore not be treated as an allowed minor upgrade without an explicit policy decision.

Subsequent local `uv-validation.json` records the same tree digest and 18/6 outcome as the manual report. Task-03 is the first clean Stop Hook + real deterministic validator recovery experiment. Its separate evidence review is now complete below; Task-02 remains INVALID FOR RECOVERY/CONVERGENCE COMPARISON.


## Task-03 clean-validator Stop Hook result

**BOUNDED_FAIL; CONTINUE EVALUATION.** Conversation `2884fc07-b900-4a46-8e41-14d05eb3efd4`, Vertex Gemini 2.5 Flash, target `~/maven-multimodule-app-stop-hook-03`, branch `openhands-poc-task-03-stop-hook`, baseline `9ea1b0ed5ca255db0fc7c659d050896d3ed5db78`.

Baseline build passed and OSV reported 24 HIGH/CRITICAL findings. Four real validator-backed hook invocations produced three denials, then allowed termination only at the configured bound. No `TranslationConfig`/missing-ADK/interpreter/report-absence failure is evidenced. Only the final full validator report survives; historical hook summaries are preserved.

Progression: attempt 1 rejects a Boot downgrade with remaining=0; feedback causes parent restoration to 4.0.6. Attempts 2, 3, and 4 report remaining=0 but reject build/test/startup. A misplaced Jackson dependency at POM line 76 causes the final Maven failure. The agent never corrects it and continues to claim the vulnerability task is complete. Terminal observations after a Git show indicate an unresolved `less` session, not verified subsequent Maven executions.

Final report: 24 resolved / 0 remaining, no-new-findings PASS, Java PASS, parent Boot PASS, suppression PASS, hygiene PASS, build FAIL, overall FAIL. **Do not call this security convergence:** OSV extracts six packages and filters all six as local/unscannable. A Boot 3.2.0 imported BOM and three untracked investigation artifacts remain despite parent-policy/hygiene PASS. Actual remediation and full behavior preservation are unproven.

The hook mechanism and same-conversation feedback chain worked without a custom retry/recovery orchestrator. The tested agent/model combination did not demonstrate adequate recovery quality. This distinction supports continued evaluation, not adoption or rejection based on bounded failure alone. Task-02's version choices must not be credited to valid deterministic feedback because its validator never ran.

Evidence and per-dimension ratings: [analysis](../experiments/openhands/GATE2-STOP-HOOK-TASK03-ANALYSIS.md), [capture/provenance](../experiments/openhands/evidence/gate2-stop-hook-task03-20261004/README.md). This review changed documentation/evidence only; target and raw runtime evidence remain untouched. No rerun, policy change, or harness redesign was performed. Gate 3 and platform adoption remain pending.
