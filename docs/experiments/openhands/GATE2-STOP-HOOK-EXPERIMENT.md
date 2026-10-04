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

## Interpretation

A PASS would prove that OpenHands' native completion-control extension point can carry the product-owned deterministic validator and drive same-conversation recovery without the old custom orchestration layer.

A bounded failure would still be useful: it would show that completion control works but does not compensate for weak engineering/evidence interpretation with the available Gemini 2.5 Flash model.

Do not add AGENTS.md, Skills, dependency recipes, or solution hints during this experiment.
