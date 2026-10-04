# OpenHands POC handoff

**Branch:** `openhands-poc-evaluation`

**Parent branch:** `context-hygiene-clone-challenge-before-commitment`

## Why this branch exists

Evaluate whether an established coding-agent harness can replace generic harness infrastructure currently implemented around Google ADK.

Do not assume the existing ADK architecture is the target design. Preserve useful principles, but first test what the established harness already provides.

## Current status

Gate 1 setup is proven manually in Google Cloud Shell:

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
    |     status: NEXT
    |
    +-- Gate 3: company-laptop package/runtime feasibility
          status: wait for Gate 2
```

## Immediate next action

Run a bounded remediation task using native OpenHands on a disposable target branch/workspace.

Do not initially inject the existing ADK Intent/Outcome schemas, recovery logic, orchestration, or known solution. The point is to observe whether OpenHands itself performs investigation, implementation, evidence-based reassessment/recovery, and self-validation.

Keep independent deterministic validation outside OpenHands.

## Explicit return point

If Gate 2 is promising, perform the corporate-laptop feasibility test. If that also passes, treat OpenHands as a qualified platform candidate and compare it fairly against OpenCode before committing to a production platform.

Do not turn the Cloud Shell npm bundle patches into production architecture by default.
