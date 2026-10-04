# Gate 2 — Native Stop Hook Validation Experiment

Status: **Task-03 reviewed: BOUNDED_FAIL with clean validator execution. Task-02 remains INVALID FOR RECOVERY/CONVERGENCE COMPARISON.**

See [Task-03 trajectory analysis](GATE2-STOP-HOOK-TASK03-ANALYSIS.md) for the completed real-validator feedback experiment, evidence limits, and unchanged CONTINUE EVALUATION decision.

See the [Task-02 evidence review](GATE2-STOP-HOOK-TASK02-INVALID-RUN.md) for the authoritative run classification and manual post-run result (18/24 findings absent, six remaining; overall FAILED). Task-01 had no deterministic completion interception. Task-02 proved interception and continuation but its validator was infrastructure-confounded. Task-03 is the first clean Stop Hook + real deterministic validator recovery experiment. **CONTINUE EVALUATION.**

The setup below records the original experiment protocol, not a pending Task-02 rerun instruction.

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

- native Stop Hook interception/feedback/continuation is **PROVEN** by Task-02 persisted events as well as the earlier dummy POC;
- Task-02 real-validator integration **FAILED / INFRASTRUCTURE-CONFOUNDED**;
- the first task-02 run is **INVALID / INFRASTRUCTURE-CONFOUNDED** for comparing remediation convergence;
- do not count its three denied completion attempts as evidence that deterministic feedback failed to improve the agent;
- do not increase retry count or add prompting;
- subsequent isolation fixes enabled Task-03; they do not repair Task-02 as experimental evidence.

Preserved evidence:

- `docs/experiments/openhands/evidence/gate2-stop-hook-20261004/run.log`
- `docs/experiments/openhands/evidence/gate2-stop-hook-20261004/last-validator.log`
- `docs/experiments/openhands/evidence/gate2-stop-hook-20261004/baseline.json`
- `docs/experiments/openhands/evidence/gate2-stop-hook-20261004/attempt-count`

The manual post-run validation has since completed: 18/24 original findings absent, six remaining, build/tests PASS, Boot policy FAIL (`unparseable`), overall FAILED. See the linked Task-02 review for all checks and evidence limits.

## Interpretation

A PASS would prove that OpenHands' native completion-control extension point can carry the product-owned deterministic validator and drive same-conversation recovery without the old custom orchestration layer.

A bounded failure is interpretable for recovery only when the validator executed correctly. Task-02 does not meet that prerequisite and cannot establish that completion control failed to improve engineering or evidence interpretation.

Do not add AGENTS.md, Skills, dependency recipes, or solution hints during this experiment.


## Validator-isolation remediation

The Stop Hook integration now isolates the deterministic validator from the ephemeral OpenHands `uv run` Python environment.

Changes:
- `openhands-gate2-validate.sh` selects a host Python outside the active `VIRTUAL_ENV` after probing `google.adk` and `pydantic` dependencies, unsets virtualenv/Python path contamination, then executes the validator with only the control repository on `PYTHONPATH`.
- Each Stop Hook attempt deletes any prior validation report before invoking the validator, preventing a stale report from masking a later infrastructure failure.
- If the validator exits without producing a fresh validation report, the hook records `hook/infrastructure-failure`, allows the conversation to terminate, and the outer runner reports `GATE2_STOP_HOOK_RESULT=INFRASTRUCTURE_FAIL` rather than consuming deterministic-denial attempts.
- Normal deterministic validation failures still return `DENY` and authoritative failure evidence to the same conversation.

The Spring Boot policy was intentionally **not** relaxed. The existing unit contract fails closed for qualifier-bearing versions such as release candidates; therefore the observed `4.2.0-M2` result remains a policy failure/unverifiable outcome rather than being silently reclassified as an allowed minor upgrade.

The later local `uv-validation.json` records a completed validator result with the same tree digest and 18/6 outcome as the manual report. Task-03 is the subsequent clean integration experiment; Task-02 remains invalid for recovery/convergence comparison.


## Task-03: first run after validator isolation

Reviewed the completed `2884fc07-b900-4a46-8e41-14d05eb3efd4` conversation against `~/maven-multimodule-app-stop-hook-03`, branch `openhands-poc-task-03-stop-hook`, original baseline `9ea1b0ed5ca255db0fc7c659d050896d3ed5db78`. State is `~/.openhands/gate2/task-03-stop-hook`.

- Baseline build passed; OSV completed with 24 HIGH/CRITICAL findings.
- Four hook invocations: three report-backed denials, then termination at the unchanged bound. No Task-02 Python import contamination is evidenced.
- First denial identifies a Boot downgrade. Same-conversation feedback causes an observed parent correction from 3.2.0 to 4.0.6.
- Later attempts fail build/test validation. The final build rejects a misplaced Jackson dependency element; the agent never repairs it.
- Final report records 24 original findings absent, zero remaining/new findings, and passing Java/parent-Boot/suppression/hygiene checks. **These checks need qualification:** all six extracted packages were filtered as local/unscannable; a Boot 3.2.0 BOM and three investigation artifacts remain. Zero findings is not proven remediation.
- Agent terminal observations show an unresolved pager interaction after the first denial. This affects recovery quality, separately from clean validator execution.
- `FINAL_STATUS=finished`, `DETERMINISTIC_VALIDATION_PASSED=False`, `GATE2_STOP_HOOK_RESULT=BOUNDED_FAIL`.

Native Stop Hook completion control is supported by real-validator evidence; adequate Gemini 2.5 Flash convergence is not demonstrated. Adoption decision remains **CONTINUE EVALUATION**. No remediation or experiment changes were made during review.

See [full trajectory and ratings](GATE2-STOP-HOOK-TASK03-ANALYSIS.md) and [auditable capture](evidence/gate2-stop-hook-task03-20261004/README.md). Earlier attempt resolved/new-finding arrays were overwritten and remain UNKNOWN; their exact failure summaries and remaining counts survive in hook events.
