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

## Research-informed assessment and immediate next action

**CONTINUE EVALUATION — not ADOPT, not REJECT.**

External OpenHands review is now recorded in the trajectory analysis. Current OpenHands SDK documentation provides native completion-control patterns (Goal Completion Loop and Stop hooks) aimed at premature completion. The exact API/behavior supported by the installed Agent Server / SDK 1.50.0 must be verified before changing the experiment.

A stronger-model isolation run is currently **blocked/deferred** because the company Vertex environment exposes only `gemini-2.5-flash` for this POC. Keep model quality marked **UNRESOLVED** rather than attributing the Gate 2 failures entirely to OpenHands or entirely to Gemini.

The next controlled experiment should therefore keep the same model, clean task baseline, task contract, tools, and deterministic validator, and change only **native completion control**. Preferred direction, if supported by the installed version: a Stop hook invoking the existing deterministic validator so that PASS permits completion and FAIL returns deterministic evidence to the same OpenHands conversation for bounded continuation.

Do not add AGENTS.md, remediation Skills, custom retry/planner/memory frameworks, dependency recipes, or additional solution hints before this experiment. Those would add variables without evidence that they address the observed failure.

If native completion control still leaves materially poor evidence interpretation or requires humans to supply engineering strategy rather than validation evidence, stop OpenHands-specific tuning and proceed to the planned OpenCode comparison under the same task/validator/model-availability constraints.

Gate 3 and platform adoption remain pending.

## Stop Hook POC

A minimal native OpenHands Stop Hook proof has been added and **PASSED on 2026-10-04**:

- `scripts/openhands/openhands-stop-hook-poc.py`
- `docs/experiments/openhands/STOP-HOOK-POC.md`

Purpose: prove, on the installed SDK 1.50.0 and existing `vertex_ai/gemini-2.5-flash` path, that the first completion attempt can be deterministically denied, feedback can be injected into the same conversation, execution can resume, and a later completion attempt can be allowed.

This is intentionally isolated from the OSS-remediation task and does not call the Gate 2 validator yet. The first execution exposed a packaging-only prerequisite: `openhands-sdk` does not include the `openhands.tools` default preset, so the POC command must also supply matching `openhands-tools==1.50.0`. The corrected run passed with two Stop-hook invocations: the first was denied, deterministic feedback was observed in the same conversation, the second was allowed, and the conversation finished. Native completion-control wiring is therefore proven for SDK/Tools 1.50.0 with Vertex Gemini 2.5 Flash.

## Explicit return point

If Gate 2 is promising, perform the corporate-laptop feasibility test. If that also passes, treat OpenHands as a qualified platform candidate and compare it fairly against OpenCode before committing to a production platform.

Do not turn the Cloud Shell npm bundle patches into production architecture by default.
