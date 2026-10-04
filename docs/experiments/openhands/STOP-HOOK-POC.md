# OpenHands Stop Hook POC

Status: **PASS — proven on 2026-10-04.**

## Purpose

This is a deliberately small experiment to prove the native completion-control path in the OpenHands stack already used by this POC.

It does **not** run the OSS-remediation task and does **not** call the Gate 2 validator.

The behavior under test is:

```text
agent attempts to finish
        ↓
native OpenHands Stop hook
        ↓
first attempt: deterministic dummy validator DENY
        ↓
feedback injected into the same conversation
        ↓
same agent continues
        ↓
later finish attempt: dummy validator ALLOW
        ↓
conversation finishes
```

The installed OpenHands SDK 1.50.0 has already been inspected in Cloud Shell and shows native `Stop` hooks plus `ALLOW` / `DENY` decisions. The local conversation implementation also shows that a denied stop returns feedback to the conversation, resets execution status to running, and continues.

## Why this comes before another Gate 2 run

Gate 2 showed that plain completion was unreliable: the agent declared success despite unresolved deterministic security failures.

Before wiring the real validator into OpenHands, this POC isolates one question only:

> Can the installed native OpenHands completion-control mechanism deny completion, feed deterministic evidence back into the same conversation, and allow a later completion attempt?

No remediation strategy, dependency logic, AGENTS.md, Skill, custom planner, or custom retry framework belongs in this test.

## Files

- `scripts/openhands/openhands-stop-hook-poc.py`

The script creates a temporary workspace and a temporary command-based Stop hook.

The dummy hook:

1. denies the first finish attempt;
2. returns feedback containing `TEST_VALIDATION_FAILED`;
3. allows the second or later finish attempt.

The agent is given only a trivial task: create `proof.txt` containing `STOP_HOOK_POC_OK` and finish.

## Preconditions

Use the same company Cloud Shell / Vertex environment as the existing OpenHands POC.

Required:

- Application Default Credentials available;
- `VERTEXAI_PROJECT` set;
- `VERTEXAI_LOCATION` set;
- Gemini model `vertex_ai/gemini-2.5-flash`;
- OpenHands SDK 1.50.0;
- OpenHands Tools 1.50.0 (the default coding-agent preset is packaged separately from the SDK).

Keep the uv cache outside the small persistent home volume:

```bash
export UV_CACHE_DIR=/tmp/openhands-uv-cache
```

If the Vertex variables are not already exported:

```bash
export VERTEXAI_PROJECT="$(gcloud config get-value project)"
export VERTEXAI_LOCATION="us-central1"
```

## Dependency note

The first POC attempt with only `openhands-sdk[vertex]==1.50.0` failed before agent startup with `ModuleNotFoundError: No module named 'openhands.tools'`. That is expected packaging behavior: the default coding-agent tools/preset live in the separate `openhands-tools` distribution. Keep SDK and tools pinned to the same 1.50.0 release so this test does not introduce a version change.

## Run

From the control repository:

```bash
cd ~/oss-remediation-adk

UV_CACHE_DIR=/tmp/openhands-uv-cache \
uv run --with "openhands-sdk[vertex]==1.50.0" \
  --with "openhands-tools==1.50.0" \
  python scripts/openhands/openhands-stop-hook-poc.py
```

This uses Gemini 2.5 Flash by default.

To make the model explicit:

```bash
UV_CACHE_DIR=/tmp/openhands-uv-cache \
uv run --with "openhands-sdk[vertex]==1.50.0" \
  --with "openhands-tools==1.50.0" \
  python scripts/openhands/openhands-stop-hook-poc.py \
  --model vertex_ai/gemini-2.5-flash
```

## Acceptance criteria

The script returns exit code 0 only when all of these are true:

1. the conversation reaches `finished`;
2. the Stop hook is invoked at least twice;
3. the first Stop event is blocked;
4. a later Stop event is allowed;
5. `TEST_VALIDATION_FAILED` appears in the persisted observable event stream;
6. the same conversation reaches the later completion attempt;
7. `proof.txt` exists with exactly `STOP_HOOK_POC_OK`.

Expected summary:

```text
FINAL_STATUS=finished
STOP_HOOK_INVOCATIONS=2
STOP_HOOK_EVENTS=2
FIRST_STOP_DENIED=True
LATER_STOP_ALLOWED=True
DENIAL_FEEDBACK_OBSERVED=True
PROOF_FILE_OK=True
POC_RESULT=PASS
```

The exact invocation/event count may be greater than two if the model attempts completion more than twice. The important properties are first denial, observed feedback, later allow, and final completion.

## Boundaries

This POC intentionally does not:

- modify `maven-multimodule-app`;
- invoke the Gate 2 deterministic validator;
- change the remediation task;
- add AGENTS.md or Skills;
- add a planner, retry manager, memory layer, or remediation recipes;
- upgrade OpenHands;
- test a stronger Gemini model, because Gemini 2.5 Flash is the only currently available company Vertex model for this POC.

The agent run is bounded by `--max-iterations` (default 12).



## Result

The POC passed on company Cloud Shell with:

```text
MODEL=vertex_ai/gemini-2.5-flash
CONVERSATION_ID=dfe7ff07-26bd-4773-a219-446ade0f8d3f
FINAL_STATUS=finished
STOP_HOOK_INVOCATIONS=2
STOP_HOOK_EVENTS=2
FIRST_STOP_DENIED=True
LATER_STOP_ALLOWED=True
DENIAL_FEEDBACK_OBSERVED=True
PROOF_FILE_OK=True
POC_RESULT=PASS
```

This proves, for the installed OpenHands SDK 1.50.0 + OpenHands Tools 1.50.0 + Vertex Gemini 2.5 Flash path, that a native Stop hook can:

1. intercept an attempted agent completion;
2. deterministically deny that completion;
3. inject failure feedback into the same conversation;
4. resume the same conversation;
5. allow a later completion attempt;
6. finish successfully without creating a custom retry/recovery orchestrator.

The proof is limited to completion-control wiring. It does not prove that the real Gate 2 validator will converge the remediation task, nor does it prove stronger reasoning quality.

## If the POC passes

Do not immediately add more agent guidance.

The next experiment is to replace only the dummy Stop hook decision with the existing Gate 2 deterministic validator:

```text
same clean Gate 2 baseline
same task contract
same Gemini 2.5 Flash
same repository/tools
same deterministic validator

only changed variable:
native OpenHands Stop hook invokes validator at attempted completion
```

Validator PASS permits completion. Validator FAIL denies completion and returns concise deterministic failure evidence to the same conversation.

That experiment should itself be bounded to a small number of denied completion attempts so a failure cannot become an unlimited recovery loop.

## If the POC fails

Do not change the remediation task.

Capture:

- script output;
- OpenHands SDK version;
- Stop Hook events;
- final conversation status;
- whether denial feedback appears in the event stream.

Treat the failure as a completion-control integration issue before spending another remediation run.
