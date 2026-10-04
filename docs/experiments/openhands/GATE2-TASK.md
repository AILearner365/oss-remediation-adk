# Gate 2 Task — Native OpenHands OSS Remediation

## Target

- Repository: `AILearner365/maven-multimodule-app`
- Baseline branch: `main-runrunning`
- Disposable working branch: `openhands-poc-task-01`
- Model path: native OpenHands -> Vertex AI -> `gemini-2.5-flash`

## Prompt to give OpenHands

```text
You are working in the repository already provided in this workspace.

Goal
-----
Resolve the identified HIGH/CRITICAL OSS dependency vulnerability or vulnerabilities in this Maven project.

Constraints
-----------
- Do not change the Java version.
- Spring Boot patch and minor upgrades are allowed when justified by the remediation.
- Do not perform a Spring Boot major-version upgrade.
- Do not downgrade Spring Boot.
- Preserve existing application behavior.
- Do not suppress, ignore, or hide vulnerability findings.
- Make only changes that are technically justified by the remediation.

Success criteria
----------------
- The target HIGH/CRITICAL vulnerability findings are resolved.
- No new HIGH/CRITICAL vulnerability finding is introduced.
- The Maven build succeeds.
- Existing tests succeed.
- The remediation is supported by repository, dependency, build/test, and available security-scanner evidence.

Investigate the problem, determine the appropriate remediation, implement it, and validate your work.
```

## Deliberately NOT provided to OpenHands

Do not add any of the following to the initial run:

- ADK Intent/Outcome schemas;
- the existing ADK lifecycle or recovery loop;
- a known remediation answer;
- a prescribed dependency version;
- a prescribed Maven edit;
- a fixed sequence of investigation steps;
- deterministic-validator feedback from outside OpenHands;
- prior failed-strategy history.

The purpose is to evaluate native OpenHands behavior, not reproduce the existing harness through prompting.

## Scanner behavior

The normal scanner/tooling available in the environment may be used by OpenHands during its own investigation and self-validation.

That agent-owned scanner usage is separate from the authoritative deterministic validation performed after OpenHands stops.

## Run-1 stop rule

For the first Gate 2 run:

```text
OpenHands works
-> OpenHands stops
-> independent deterministic validation runs
-> record PASS or FAIL
-> stop
```

Do not automatically feed deterministic-validation failures back into OpenHands in run 1.
