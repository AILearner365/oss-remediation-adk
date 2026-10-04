# Gate 2 — Native Stop Hook Validation Experiment

Status: **READY TO RUN.**

## Objective

Test whether native OpenHands completion control materially improves the same OSS-remediation task without reintroducing custom agent orchestration.

This experiment changes one variable from the original Gate 2 native run:

```text
plain OpenHands completion
        ↓
native OpenHands Stop hook
        ↓
existing deterministic Gate 2 validator
```

Everything else stays fixed:

- task contract;
- Gemini 2.5 Flash;
- native OpenHands agent;
- repository problem;
- build/scanner semantics;
- deterministic acceptance criteria.

## Target branch and workspace

A fresh disposable target branch was created from `main-runrunning`:

```text
AILearner365/maven-multimodule-app
branch: openhands-poc-task-02-stop-hook
```

Preserve the original Gate 2 workspace and evidence. Use a Git worktree for this experiment:

```bash
cd ~/maven-multimodule-app
git fetch origin main-runrunning openhands-poc-task-02-stop-hook

git worktree add \
  ~/maven-multimodule-app-stop-hook \
  -b openhands-poc-task-02-stop-hook-local \
  origin/openhands-poc-task-02-stop-hook
```

If the local branch name created by the worktree command differs from the remote task branch, switch it so the checked-out branch is exactly `openhands-poc-task-02-stop-hook`. The deterministic baseline requires the exact task branch name. A simpler alternative when no local branch of that name exists is:

```bash
git worktree add \
  ~/maven-multimodule-app-stop-hook \
  openhands-poc-task-02-stop-hook
```

Before running the baseline, verify:

```bash
cd ~/maven-multimodule-app-stop-hook
git branch --show-current
git status --short
git rev-parse HEAD
git rev-parse origin/main-runrunning
```

The branch must be `openhands-poc-task-02-stop-hook`, the tree must be clean, and HEAD must equal `origin/main-runrunning`.

## 1. Prepare the fresh task branch

From the control repo:

```bash
cd ~/oss-remediation-adk

TARGET_REPO="$HOME/maven-multimodule-app-stop-hook" \
TASK_BRANCH="openhands-poc-task-02-stop-hook" \
bash scripts/openhands/openhands-gate2-prepare.sh
```

The preparation script must pass without resetting or overwriting anything.

## 2. Capture a fresh deterministic baseline

Use a separate state directory so this experiment cannot overwrite task-01 evidence:

```bash
mkdir -p ~/.openhands/gate2/task-02-stop-hook

cd ~/oss-remediation-adk

bash scripts/openhands/openhands-gate2-baseline.sh \
  --target-repo "$HOME/maven-multimodule-app-stop-hook" \
  --base-branch main-runrunning \
  --task-branch openhands-poc-task-02-stop-hook \
  --state-file "$HOME/.openhands/gate2/task-02-stop-hook/baseline.json"
```

Do not continue unless the baseline build passes and HIGH/CRITICAL findings are present.

## 3. Run OpenHands with native Stop-hook validation

Set the existing Vertex environment:

```bash
export UV_CACHE_DIR=/tmp/openhands-uv-cache
export VERTEXAI_PROJECT="deutschebank-aipocs"
export VERTEXAI_LOCATION="us-central1"
```

Run:

```bash
cd ~/oss-remediation-adk

UV_CACHE_DIR=/tmp/openhands-uv-cache \
uv run \
  --with "openhands-sdk[vertex]==1.50.0" \
  --with "openhands-tools==1.50.0" \
  python scripts/openhands/openhands-gate2-stop-hook-run.py
```

The runner reads the exact prompt from `GATE2-TASK.md`; do not add hints.

## Completion behavior

At each attempted finish:

```text
OpenHands attempts Finish
        ↓
native Stop hook
        ↓
existing Gate 2 deterministic validator
        ↓
PASS
  → Stop hook ALLOW
  → conversation can finish

FAIL
  → Stop hook DENY
  → concise deterministic failure evidence is injected
  → same conversation returns to RUNNING
  → OpenHands chooses its own next engineering action
```

The hook does not prescribe dependency versions, Maven edits, or recovery strategy.

## Bound

Default: at most **3 denied completion attempts**.

If validation still fails after those denied attempts, the next attempted stop is allowed only to terminate the experiment. This is **not acceptance**. The outer runner reads the last deterministic report and returns:

```text
GATE2_STOP_HOOK_RESULT=BOUNDED_FAIL
```

unless deterministic validation actually passed.

This distinction preserves:

```text
agent termination != deterministic success
```

## New files

- `scripts/openhands/openhands-gate2-stop-hook.sh`
  - native command Stop-hook adapter;
  - invokes the existing Gate 2 validator;
  - returns ALLOW on validator PASS;
  - returns DENY plus concise deterministic evidence on validator FAIL;
  - contains no remediation strategy.

- `scripts/openhands/openhands-gate2-stop-hook-run.py`
  - starts native OpenHands against the fresh task-02 workspace;
  - uses Gemini 2.5 Flash;
  - loads the existing task prompt;
  - configures the native Stop hook;
  - persists conversation evidence;
  - reports deterministic acceptance separately from conversation termination.

## Evaluation

Compare this run against the captured task-01 native/recovery trajectory on:

- deterministic PASS/FAIL;
- number of completion attempts;
- whether deterministic failure evidence changes strategy;
- constraint adherence;
- repeated/unproductive actions;
- self-validation;
- completion judgment;
- total observable actions/time.

Do not judge success merely because the conversation reaches `finished`.

## First execution result — INVALID FOR REMEDIATION COMPARISON

The first task-02 Stop Hook execution reached the configured bound:

```text
STOP_HOOK_INVOCATIONS=4
DENIED_COMPLETIONS=3
DETERMINISTIC_VALIDATION_PASSED=False
GATE2_STOP_HOOK_RESULT=BOUNDED_FAIL
```

However, review of the preserved evidence shows that this **must not be interpreted as three genuine deterministic remediation failures**.

Every Stop-hook validator invocation failed before deterministic validation could run. The preserved `last-validator.log` ends during Python import with:

```text
AttributeError: module 'google.genai.types' has no attribute 'TranslationConfig'
```

The Stop-hook command was running inside the `uv run` OpenHands environment. Its child validator process mixed the existing system Google ADK installation with packages from the ephemeral OpenHands uv environment, producing an incompatible Python dependency set. No `validation.json` was produced.

The hook adapter treated the validator process error as a normal validation failure, so it returned `DENY` three times. The agent therefore received infrastructure-error feedback rather than authoritative Maven/OSV/constraint findings. The agent correctly recognized the repeated `TranslationConfig` traceback as external to the Maven repository, although it still continued to assert task completion.

Therefore:

- native Stop Hook interception/feedback/continuation remains **PROVEN** by the earlier dummy POC;
- task-02 completion-control integration is **NOT YET VALIDATED** with the real deterministic validator;
- the first task-02 run is **INVALID / INFRASTRUCTURE-CONFOUNDED** for comparing remediation convergence;
- do not count its three denied completion attempts as evidence that deterministic feedback failed to improve the agent;
- do not increase retry count or add prompting;
- fix validator environment isolation first, then rerun from a fresh clean task baseline.

Preserved evidence:

- `docs/experiments/openhands/evidence/gate2-stop-hook-20261004/run.log`
- `docs/experiments/openhands/evidence/gate2-stop-hook-20261004/last-validator.log`
- `docs/experiments/openhands/evidence/gate2-stop-hook-20261004/baseline.json`
- `docs/experiments/openhands/evidence/gate2-stop-hook-20261004/attempt-count`

Before any rerun, manually execute the deterministic validator outside the OpenHands `uv run` environment against the preserved task-02 workspace. This confirms both the actual final repository result and the Python environment that the Stop Hook must invoke.

## Interpretation

A PASS would prove that OpenHands' native completion-control extension point can carry the product-owned deterministic validator and drive same-conversation recovery without the old custom orchestration layer.

A bounded failure would still be useful: it would show that completion control works but does not compensate for weak engineering/evidence interpretation with the available Gemini 2.5 Flash model.

Do not add AGENTS.md, Skills, dependency recipes, or solution hints during this experiment.


## Validator-isolation remediation

The Stop Hook integration now isolates the deterministic validator from the ephemeral OpenHands `uv run` Python environment.

Changes:
- `openhands-gate2-validate.sh` selects the first host `python3` outside the active `VIRTUAL_ENV`, unsets virtualenv/Python path contamination, then executes the validator with only the control repository on `PYTHONPATH`.
- Each Stop Hook attempt deletes any prior validation report before invoking the validator, preventing a stale report from masking a later infrastructure failure.
- If the validator exits without producing a fresh validation report, the hook records `hook/infrastructure-failure`, allows the conversation to terminate, and the outer runner reports `GATE2_STOP_HOOK_RESULT=INFRASTRUCTURE_FAIL` rather than consuming deterministic-denial attempts.
- Normal deterministic validation failures still return `DENY` and authoritative failure evidence to the same conversation.

The Spring Boot policy was intentionally **not** relaxed. The existing unit contract fails closed for qualifier-bearing versions such as release candidates; therefore the observed `4.2.0-M2` result remains a policy failure/unverifiable outcome rather than being silently reclassified as an allowed minor upgrade.

Before a fresh agent rerun, verify the updated validator against the preserved task-02 workspace from inside the same OpenHands `uv run` dependency context. It should now execute and produce a validation report rather than a `TranslationConfig` import traceback.
