# Gate 2 Orchestrated Runbook

Status: **Ready for the next clean Gate 2 run.**

This runbook is the operational entry point for the current OpenHands Gate 2 experiment. It documents the staged Cloud Shell workflow, environment handling, clean task setup, deterministic baseline, native OpenHands execution, Stop Hook validation, evidence capture, and automatic evidence publication.

The normal operator command is intentionally one command:

```bash
cd ~/oss-remediation-adk
git pull
bash scripts/openhands/openhands-gate2-fresh-run.sh
```

An explicit task id remains supported when needed:

```bash
bash scripts/openhands/openhands-gate2-fresh-run.sh 07
```

## Execution model

The orchestrator runs three independently executable stages:

```text
STARTUP / PREPARE
        |
        v
VERIFY
        |
        v
EXECUTE
        |
        +--> clean task branch/worktree/state
        +--> deterministic baseline
        +--> OpenHands remediation run
        +--> native Stop Hook validation/recovery
        +--> evidence capture and publication
```

Each stage fails closed. A later stage does not run when an earlier stage fails.

## Stage 1 — Startup / Prepare

Script:

```bash
bash scripts/openhands/openhands-cloudshell-startup.sh
```

This stage prepares or safely repairs the known Cloud Shell POC runtime by delegating to the guarded `openhands-cloudshell-poc.sh prepare` path.

It:

- checks required runtime commands such as Node, npm, uv, gcloud, tmux, and Python;
- ensures the pinned Agent Canvas version is present;
- refuses to silently adapt to an unexpected Canvas version;
- resolves the Vertex environment using the shared resolver;
- synchronizes the active gcloud project to the resolved Vertex project when required;
- verifies ADC availability;
- prepares the uv cache under `/tmp`;
- creates/repairs the OpenHands tmux directory;
- reapplies the two known guarded Vertex/Canvas POC patches when required;
- prints the effective patch state and disk usage.

The shared environment resolver is:

```text
scripts/openhands/openhands-cloudshell-env.sh
```

Vertex project precedence is:

```text
VERTEXAI_PROJECT
    -> GOOGLE_CLOUD_PROJECT
    -> active gcloud project
    -> POC fallback: deutschebank-aipocs
```

The location defaults to `us-central1` and the uv cache defaults to `/tmp/openhands-uv-cache`.

## Stage 2 — Verify

Script:

```bash
bash scripts/openhands/openhands-cloudshell-verify.sh
```

Verification is intentionally non-repairing. It proves that Startup left a usable runtime rather than silently fixing missing pieces itself.

It verifies:

- expected prepared Agent Canvas/runtime version;
- required Vertex launcher patch;
- required Vertex ADC readiness patch;
- tmux can actually create a session using the OpenHands tmux directory;
- ADC works;
- effective Vertex project/location are available;
- the uv runtime directory exists;
- a real OpenHands SDK request to `vertex_ai/gemini-2.5-flash` succeeds.

If Verify fails, Execute does not start. Fix or rerun Startup as appropriate, then Verify can be rerun independently.

## Stage 3 — Execute

Script:

```bash
bash scripts/openhands/openhands-gate2-execute.sh <task-id>
```

The normal orchestrator invokes this automatically. Execute owns experiment-specific setup and execution only.

It:

1. resolves the same shared Vertex environment used by Startup/Verify;
2. verifies the source target repository and expected origin;
3. fetches `main-runrunning`;
4. creates or safely reuses the disposable task branch only when it is exactly at the baseline;
5. refuses a contaminated/diverged task branch;
6. creates an isolated Git worktree;
7. creates an isolated Gate 2 state directory;
8. runs the deterministic baseline;
9. launches the native OpenHands agent through Vertex Gemini 2.5 Flash;
10. uses the current task contract from `GATE2-TASK.md`;
11. uses native OpenHands Stop Hook completion control;
12. preserves the conversation/runtime state for analysis.

The target naming convention is:

```text
branch:    openhands-poc-task-<NN>-stop-hook
worktree:  ~/maven-multimodule-app-stop-hook-<NN>
state:     ~/.openhands/gate2/task-<NN>-stop-hook
```

## Automatic task numbering

When no task id is supplied, the orchestrator chooses the next numeric task id after the highest matching task branch, worktree, or state directory it can see. The minimum next id is `05`.

Example:

```text
highest existing task = 04
next run = 05

highest existing task = 05
next run = 06
```

An explicitly supplied numeric task id overrides automatic selection.

## Deterministic baseline

Before the agent starts, Execute runs:

```text
scripts/openhands/openhands-gate2-baseline.sh
```

The baseline records the pre-agent repository/build/security state into the task state directory. The agent does not start if required baseline preparation fails.

The authoritative deterministic scanner path remains the configured OSV Scanner path used by the baseline/validator. The task prompt also exposes `~/bin/osv-scanner` to OpenHands as optional investigation/self-validation evidence without prescribing when or how the agent must use it.

## OpenHands execution and completion control

OpenHands owns the engineering work:

```text
investigate
-> reason from available evidence
-> edit
-> build/test/scan as it chooses
-> reassess
-> self-validate
-> attempt completion
```

At each attempted completion:

```text
OpenHands attempts to finish
        |
        v
native Stop Hook
        |
        v
independent deterministic validator
        |
        +-- PASS -> completion allowed
        |
        +-- FAIL -> decision-critical failure evidence is returned
                   to the same conversation
                   -> OpenHands continues
```

The Stop Hook does not prescribe a dependency version, Maven edit, or remediation strategy.

The configured default experiment bound remains three denied completion attempts. If the bound is exhausted, a later stop may be allowed only to terminate the experiment; deterministic acceptance remains false unless the validator actually passed.

## Evidence captured for every orchestrated run

Local orchestration logs are written under:

```text
~/.openhands/gate2/run-logs/run-<UTC timestamp>/
```

The local bundle includes:

- `startup.log`
- `verify.log`
- `execute.log`
- `combined.log`
- `task-id.txt`
- `status.txt`
- `evidence-export.log` when trajectory export runs

On exit — success or failure — the orchestrator creates a reviewable evidence directory:

```text
docs/experiments/openhands/evidence/gate2-orchestrated-run-<UTC timestamp>/
```

It captures, when available:

- startup/verify/execute/combined logs;
- stage and exit status;
- run metadata including task id, control commit, model, Vertex project/location, iteration and denial bounds;
- deterministic `baseline.json`;
- final `validation.json`;
- every preserved Stop Hook validation attempt:
  - `validation-attempt-N.json`
  - `validator-attempt-N.log`;
- Stop Hook attempt counter and infrastructure-failure marker;
- sanitized observable OpenHands event trajectory;
- event manifest/hashes;
- final target Git branch/HEAD/status;
- final tracked diff and diff statistics.

### Observable trajectory coverage

The trajectory export is designed for engineering-behavior analysis. It preserves the ordered observable record needed to evaluate:

- user/assistant messages;
- actions;
- tool calls and arguments;
- tool observations/results;
- command failures and exit status when present in observations;
- file-edit activity represented in SDK events;
- execution-state changes;
- Stop Hook decisions;
- deterministic feedback returned to the agent;
- timestamps and event sequence.

This supports later analysis of:

```text
evidence available
-> action selected
-> observed result
-> next action
-> strategy change or repetition
-> recovery behavior
-> self-validation
-> completion judgment
```

Internal/private model chain-of-thought is intentionally not part of the published evidence standard. The exporter excludes internal reasoning/thought fields, opaque provider thought signatures, raw LLM responses, and other unreviewed/private payloads. Unknown SDK event kinds retain their sequence/kind metadata while unreviewed payload fields are omitted.

## Automatic evidence publication

After capture, the orchestrator stages **only** the run evidence directory in the control repository, creates an evidence commit, and pushes it to:

```text
openhands-poc-evaluation
```

This happens on successful and failed runs when possible.

Automatic evidence publication does **not** commit or deliver the target repository's remediation changes. A failed or unreviewed remediation must not be promoted as delivery merely because evidence was published.

If evidence push fails, the run evidence remains available locally and in the control-repository evidence directory for manual recovery. Set:

```bash
AUTO_PUSH_EVIDENCE=0
```

only when automatic evidence commit/push is intentionally disabled.

## Failure behavior

```text
Startup fails
  -> Verify/Execute do not run
  -> startup/combined/status evidence captured

Verify fails
  -> Execute does not run
  -> startup/verify/combined/status evidence captured

Baseline fails
  -> OpenHands does not start
  -> execution/baseline-related evidence retained when produced

OpenHands/Stop Hook/validator fails
  -> current task/conversation/validator evidence retained
  -> run exits nonzero according to the existing result semantics

Evidence publication fails
  -> experiment result is not converted into success
  -> local evidence remains available for recovery
```

## Independent troubleshooting commands

The stages remain independently runnable:

```bash
# Prepare or repair the environment
bash scripts/openhands/openhands-cloudshell-startup.sh

# Verify the already-prepared environment
bash scripts/openhands/openhands-cloudshell-verify.sh

# Execute only a specific clean experiment
bash scripts/openhands/openhands-gate2-execute.sh 05
```

The normal path should still be the single orchestrator command so that task numbering, logging, evidence capture, and automatic publication are consistent.

## Operator command for the next run

```bash
cd ~/oss-remediation-adk
git pull
bash scripts/openhands/openhands-gate2-fresh-run.sh
```

No task number is required unless an explicit task id is desired.

## Scope boundary

This orchestration exists to make the evaluation reproducible and auditable. It must not grow into a custom agent planner/retry/reasoning framework.

The intended responsibility split remains:

```text
OpenHands/model:
  investigation
  engineering judgment
  implementation
  reassessment
  recovery
  self-validation

Product/evaluation layer:
  task/constraints
  environment readiness
  deterministic baseline
  independent deterministic validation
  evidence retention
  experiment bounds
  delivery decision
```

Do not add remediation recipes, a custom planner, custom memory/retry orchestration, or solution hints merely to make the model succeed.
