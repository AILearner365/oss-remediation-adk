# Gate 2 — Native OpenHands Remediation Experiment

## Objective

Determine whether native OpenHands can perform a real OSS-remediation task with minimal product-layer prompting.

This experiment intentionally does not import the existing ADK orchestration into OpenHands.

## Repository separation

Control/evaluation material lives here:

```text
AILearner365/oss-remediation-adk
branch: openhands-poc-evaluation
```

The repository OpenHands modifies is:

```text
AILearner365/maven-multimodule-app
baseline: main-runrunning
working branch: openhands-poc-task-01
```

The remote `openhands-poc-task-01` branch was created directly from `main-runrunning`.

## Why main-runrunning

`main-runrunning` is the established vulnerable application baseline used by the recent autonomous-remediation experiments. It also contains the later Spring Boot web-module run support that is not present on `main` / `main-run`.

Do not use an old `autonomous-oss-remediation-*` result branch as the Gate 2 baseline.

## Gate 2 phases

### 1. Prepare

Use:

```bash
bash scripts/openhands/openhands-gate2-prepare.sh
```

The preparation script does not run an agent. It verifies the local target checkout, requires a clean working tree, fetches the two Gate 2 refs, checks out `openhands-poc-task-01`, and verifies that its starting point is based on `main-runrunning`.

It does not reset or delete local work.

### 2. Verify the vulnerability baseline

Before giving the task to OpenHands, confirm that the prepared target branch still contains an in-scope HIGH/CRITICAL finding using the approved scanner path.

This is a deterministic precondition. If the scan is clean or incomplete, do not run the agent; investigate the test fixture/environment instead.

The existing autonomous-remediation deterministic scanner remains the reference implementation for authoritative scan semantics.

### 3. Run native OpenHands

Point OpenHands at the prepared `maven-multimodule-app` checkout and give it only the task in `GATE2-TASK.md`.

Do not give it the old ADK lifecycle, Intent/Outcome format, recovery loop, or known answer.

Observe whether the native harness performs:

```text
investigate
-> reason
-> implement
-> observe evidence
-> reassess when evidence contradicts the strategy
-> recover/change strategy
-> self-validate
```

Do not intervene unless the failure is an environment/tool-access problem rather than an engineering decision.

### 4. Independent deterministic validation

After OpenHands stops, validate the final repository independently from OpenHands.

The authoritative checks are the same product-owned checks already represented by the deterministic validation layer:

- repository remains based on the recorded baseline;
- Maven build/test/startup checks;
- fresh vulnerability scan;
- target finding comparison;
- no new prohibited HIGH/CRITICAL findings;
- Java version protection;
- Spring Boot version policy: patch/minor allowed, major/downgrade rejected;
- suppression policy;
- repository diff/change evidence.

For Gate 2 run 1, validation is terminal evidence. Do not automatically route a failure back into OpenHands.

## Evaluation record

Capture at least:

- final PASS/FAIL;
- OpenHands investigation quality;
- dependency-path reasoning;
- chosen remediation strategy;
- changed files;
- build/test/scanner evidence used by OpenHands;
- any material failure observed during the run;
- whether that evidence changed its reasoning;
- whether it repeated a failed strategy;
- self-validation behavior;
- independent deterministic-validation result;
- elapsed time and model usage when observable;
- amount of custom prompting/configuration required.

## Interpretation

A successful code change alone is not sufficient.

The strongest Gate 2 result is evidence that OpenHands itself can investigate, make an engineering decision, react to new evidence, revise when necessary, and self-validate without the old orchestration being recreated around it.
