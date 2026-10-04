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
    |     status: native + one recovery completed; both validators FAILED; CONTINUE EVALUATION
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

## Immediate next action

Research the official/community questions at the end of the trajectory report before deciding the next experiment. Preserve the native and recovery phases separately; judge engineering decisions and reassessment as well as deterministic acceptance.

Do not rerun OpenHands, change the target remediation, or redesign the harness as part of this evidence-capture task. No custom orchestration, AGENTS.md, Skills, retry loops, or new framework code is recommended at this stage. Gate 3 and platform adoption remain pending.

## Explicit return point

If Gate 2 is promising, perform the corporate-laptop feasibility test. If that also passes, treat OpenHands as a qualified platform candidate and compare it fairly against OpenCode before committing to a production platform.

Do not turn the Cloud Shell npm bundle patches into production architecture by default.
