# OpenHands POC handoff

**Branch:** `openhands-poc-evaluation`

**Parent branch:** `context-hygiene-clone-challenge-before-commitment`

## Why this branch exists

Evaluate whether an established coding-agent harness can replace generic harness infrastructure currently implemented around Google ADK.

Do not assume the existing ADK architecture is the target design. Preserve useful principles, but first test what the established harness already provides.

## Current status

Gate 1 setup is proven and has a repeatable `verify` health check in Google Cloud Shell:

- Agent Canvas 1.24.0
- Agent Server / SDK 1.50.0
- native OpenHands agent
- Vertex AI through ADC
- `vertex_ai/gemini-2.5-flash`
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
    |     status: PREPARED — target branch and task/control docs created; baseline scan + native run are next
    |
    +-- Gate 3: company-laptop package/runtime feasibility
          status: wait for Gate 2
```

## Gate 2 prepared state

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

## Immediate next action

1. Pull `openhands-poc-evaluation` in Cloud Shell.
2. Run the guarded Gate 2 preparation script against the existing `maven-multimodule-app` checkout.
3. Verify the HIGH/CRITICAL vulnerability baseline with the approved scanner before starting the agent.
4. Point native OpenHands at the prepared target checkout and give it only `GATE2-TASK.md`.
5. After OpenHands stops, run independent deterministic validation and record PASS/FAIL. For run 1, do not automatically feed validation failure back to OpenHands.

Do not initially inject the existing ADK Intent/Outcome schemas, recovery logic, orchestration, or known solution. The point is to observe whether OpenHands itself performs investigation, implementation, evidence-based reassessment/recovery, and self-validation.

## Explicit return point

If Gate 2 is promising, perform the corporate-laptop feasibility test. If that also passes, treat OpenHands as a qualified platform candidate and compare it fairly against OpenCode before committing to a production platform.

Do not turn the Cloud Shell npm bundle patches into production architecture by default.
