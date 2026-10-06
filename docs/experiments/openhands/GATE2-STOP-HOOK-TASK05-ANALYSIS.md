# Gate 2 Task-05: orchestrated Stop Hook trajectory analysis

## Executive result

**Result: BOUNDED_FAIL. Decision: CONTINUE EVALUATION, but stop adding OpenHands-specific tuning for this model/task unless a new platform capability gap is proven.**

Task-05 is the first run using the fully staged orchestrator, automatic evidence capture, per-attempt validator snapshots, explicit OSV Scanner availability in the task contract, and decision-critical Stop Hook feedback with finding identities/current package versions.

The orchestration/evidence path worked. The remediation did not converge.

Baseline: 25 HIGH/CRITICAL findings. Attempt 1 resolved exactly 2 targets and left 23. Attempts 2-4 lost comparable scan evidence entirely: the build failed, the fresh scan became incomplete, all 25 baseline targets moved to UNKNOWN/unscannable, Java policy failed, and Spring Boot policy failed. Attempt 4 terminated only because the configured bound was reached.

The dominant failure is not missing completion interception or missing feedback transport. It is evidence interpretation and strategy selection after authoritative feedback.

## Scope and evidence

Reviewed the completed Task-05 run without rerunning OpenHands, Maven, OSV, or the deterministic validator.

- Control branch: `openhands-poc-evaluation`
- Target branch: `openhands-poc-task-05-stop-hook`
- Baseline commit: `9ea1b0ed5ca255db0fc7c659d050896d3ed5db78`
- Model: `vertex_ai/gemini-2.5-flash`
- Conversation: `d39c00c206a94097a1139edffb1059be`
- Evidence: `docs/experiments/openhands/evidence/gate2-orchestrated-run-20261006T002206Z/`

The observable trajectory contains 407 events:

- 193 actions
- 193 observations
- 8 messages
- 4 Stop Hook events
- 8 condensations
- 1 system-prompt event

No hidden chain-of-thought is used. Conclusions are based on messages, actions, observations, deterministic reports, final Git state, and external source verification where explicitly identified.

## Baseline drift versus Task-04

Task-04 had 24 HIGH/CRITICAL baseline findings. Task-05 has 25 on the same baseline commit.

The added Task-05 finding is:

`CVE-2026-47884 | org.springframework:spring-webmvc@7.0.7 | CRITICAL | fixed 7.0.9`

This is scanner/advisory-feed drift, not a repository change. Therefore raw counts between Task-04 and Task-05 are not perfectly comparable. Behavioral transitions within Task-05 remain valid.

## Attempt-by-attempt result

| Boundary | Build | Security comparison | Boot | Java | New prohibited | Result |
| --- | --- | --- | --- | --- | --- | --- |
| Baseline | PASS | 25 targets | 4.0.6 baseline | protected baseline | n/a | ready |
| Attempt 1 | PASS | 2 resolved / 23 remaining / 0 unknown | PASS | PASS | 0 | DENY |
| Attempt 2 | FAIL | comparison incomplete / 25 unknown | FAIL: configuration changed + downgrade | FAIL | unavailable | DENY |
| Attempt 3 | FAIL | comparison incomplete / 25 unknown | FAIL | FAIL | unavailable | DENY |
| Attempt 4 | FAIL | comparison incomplete / 25 unknown | FAIL; final parent 2.7.18 | FAIL | unavailable | termination only |

All four validator attempts survive as complete JSON and log snapshots in the evidence bundle.

## Before attempt 1: useful narrow fix, incorrect self-validation

The agent ran the exposed OSV Scanner immediately. The scan found the five POMs and direct dependencies but also reported Maven transitive-resolution failures for local reactor modules. The terminal exit code was nonzero.

The agent then read the JSON output and focused on the two direct root dependencies:

- Commons Text 1.9 -> 1.10.0
- org.json 20230227 -> 20231013

It implemented those two exact fixed-version upgrades and ran a successful Maven build.

The second agent-owned OSV scan again reported Maven resolution failures and exited nonzero (127), but its JSON file contained `"results": []`. The agent treated the empty JSON as proof that no HIGH/CRITICAL vulnerabilities remained and attempted completion.

The first deterministic validator disproved that conclusion:

- 2 of 25 resolved
- 23 remained
- build/tests passed
- no new prohibited findings
- Boot policy passed
- Java policy passed

**Assessment:** the initial remediation itself was valid but incomplete. The first completion failure is an evidence-interpretation failure: the agent ignored an explicit scanner-resolution error and treated an incomplete empty result as authoritative success.

## Denial 1 -> attempt 2: first material divergence

Stop Hook feedback listed the 23 remaining identities and their current package versions.

The first material strategy change after that feedback is immediate:

`E00027: Spring Boot parent 4.0.6 -> 3.2.5`

This directly violates the task's no-downgrade constraint.

It also creates the central technical failure that dominates the rest of the run. The repository uses `spring-boot-starter-webmvc`, which is a Spring Boot 4 coordinate. Spring Boot 3.2 uses `spring-boot-starter-web`, not `spring-boot-starter-webmvc`.

External verification:

- Spring Boot 3.2.5 documentation lists `spring-boot-starter-web` as the MVC web starter.
- The Spring Boot 4 migration guide records the rename `spring-boot-starter-web -> spring-boot-starter-webmvc`.
- Spring Boot 4 documentation lists `spring-boot-starter-webmvc` as the current MVC starter.

Therefore the subsequent Maven error that `spring-boot-starter-webmvc:3.2.5` cannot be resolved is a predictable cross-major coordinate mismatch, not evidence that Maven Central or the network is generally broken.

### 404 file contamination

At E00081 the agent runs:

`curl -o spring-boot-starter-webmvc-3.2.5.pom https://repo.maven.apache.org/.../3.2.5/...pom`

Because curl was not invoked with `--fail`, HTTP 404 content was saved as a local file while curl exited 0. The downloaded file is only 554 bytes and is HTML, not a Maven POM.

That untracked file later becomes part of the deterministic scan input and causes:

`XML syntax error ... element <hr> closed by </body>`

This is the direct cause of the later fresh-scan `INCOMPLETE_FATAL_FAILURE`.

The run therefore contains a clear causal chain:

```text
authoritative denial with remaining identities
-> forbidden Boot downgrade
-> Boot-4-only starter coordinate retained under Boot 3
-> nonexistent artifact
-> HTTP 404 saved as .pom
-> malformed file enters scanner workspace
-> deterministic scan becomes incomplete
-> all baseline targets become UNKNOWN
```

This is an agent/tool-use trajectory, not a validator defect.

## Excessive strategy churn after denial 1

Between the first and second hook boundaries the agent performs 82 actions: 55 file-editor actions and 27 terminal actions.

Across the whole run it executes:

- 193 actions total
- 84 `str_replace` edits
- 31 file views
- 39 `mvn clean install -U` runs
- 9 additional `mvn clean install` runs
- 2 full local Maven repository deletions

The run repeatedly changes parent/BOM management, starter versions, plugin versions, module parents, repository declarations, compiler properties, and local Maven caches.

The first denial did not produce focused remaining-target analysis. It caused broad platform reconfiguration around a forbidden downgrade.

## Denial 2 -> attempt 3: policy correction attempted, then abandoned

Attempt 2 feedback is stronger than earlier experiments. It explicitly reports:

- build failure
- fresh scan incomplete
- target comparison unavailable
- 25 UNKNOWN baseline targets
- Java policy violation
- Spring Boot configuration change + downgrade

The agent initially reacts correctly:

- E00197 restores parent 4.0.6
- E00201/E00205 remove explicit module versions
- E00207 removes broad explicit starter management

But at E00211 it changes the parent back to 3.2.5.

So the feedback causes a temporary correction, not a durable strategy change.

Attempt 3 therefore reaches the same deterministic state as attempt 2: build failure, scan incomplete, 25 unknown, Java/Boot policy failures.

**Classification: NO PROGRESS.**

## Denial 3 -> attempt 4: strongest evidence opportunity, then regression

After the third denial, the agent again restores the parent to 4.0.6.

This time it reaches a genuinely useful state:

- E00261: Maven build succeeds on Boot 4.0.6
- E00269: aggregate CycloneDX SBOM generation succeeds
- E00271: OSV over the SBOM reports 47 known vulnerabilities across 11 affected packages
- E00293: another Maven build succeeds after repairing a malformed dependencyManagement edit
- E00297: the SBOM scan still reports the vulnerable dependency set
- E00302: dependency tree correctly shows the current Jackson family:
  - `tools.jackson.core:jackson-databind:3.1.2`
  - `tools.jackson.core:jackson-core:3.1.2`

This is important: by this point, the environment, Maven, scanner, dependency tree, and direct evidence acquisition are all functioning. The model has enough evidence to reason from the actual Boot 4 dependency platform.

Instead, the agent changes the parent back to 3.2.5 at E00303 and resumes the same missing-artifact strategy.

Later it performs two decisive checks:

- `mvn dependency:get ... spring-boot-starter-webmvc:3.2.5` -> artifact absent in Maven Central
- `curl -I ... spring-boot-starter-webmvc/3.2.5/...pom` -> HTTP 404 / NoSuchKey

Even after direct proof that the coordinate does not exist, the agent interprets the failure as an external network/proxy/Maven-environment problem rather than reconsidering the Boot-major/coordinate mismatch.

It ultimately downgrades Spring Boot again, this time to 2.7.18, clears the Maven repository, and attempts another build.

This is the strongest Task-05 evidence that the principal gap is evidence interpretation/strategy, not inability to obtain evidence.

## Why the environment explanation is contradicted by the run

The agent's completion messages repeatedly attribute the missing 3.2.5 artifact to network restrictions, proxies, Maven installation, or repository availability.

The observable record contradicts a general Maven Central access problem:

- many Maven Central POMs/JARs download successfully;
- Spring Boot parent/dependencies 3.2.5 download successfully;
- the build succeeds under the original Boot 4.0.6 state;
- curl reaches Maven Central and receives an explicit 404 `NoSuchKey` for the requested 3.2.5 webmvc artifact.

External Spring documentation independently confirms the coordinate mismatch.

Therefore the environment explanation is unsupported.

## Fixed-version evidence that was available

The deterministic Task-05 baseline itself already carries fixed-version evidence for the vulnerable families, for example:

- Spring Expression 7.0.7 -> fixed 7.0.8
- Spring Web MVC 7.0.7 -> fixes include 7.0.8 and, for the newly added critical CVE, 7.0.9
- Micrometer 1.16.5 -> fixed 1.16.6 for the two recorded HIGH findings
- Tomcat 11.0.21 -> recorded fixed releases include 11.0.22 and 11.0.25 depending on finding
- Jackson 3.1.2 -> recorded fixed releases include 3.1.4, 3.1.6 and 3.1.7 depending on finding

This does not prescribe the correct remediation, because compatibility still has to be reasoned about and validated. It does demonstrate that the evidence pointed toward compatible-family investigation rather than an unexplained downgrade to Boot 3.2.5 or 2.7.18.

External Spring documentation also shows current stable Boot 4 lines exist, including 4.0.x and 4.1.x. Under the task contract, patch/minor movement from 4.0.6 was within the allowed search space; major downgrade was explicitly prohibited.

## Comparison with Task-03 and Task-04

| Dimension | Task-03 | Task-04 | Task-05 |
| --- | --- | --- | --- |
| Baseline targets | 24 | 24 | 25 (feed drift) |
| Initial feedback effect | fixes parent downgrade | remaining 22 -> 13 but introduces regressions | resolves only 2 direct targets, then downgrades Boot |
| Final build | FAIL | PASS | FAIL |
| Final scan comparability | collapsed/false zero | complete | incomplete; 25 UNKNOWN |
| Boot policy | final parent restored, older BOM remained | FAIL 4.0.6 -> 3.3.1 | FAIL; final 2.7.18 |
| Pager/tool-state issue | yes | no | no |
| Security convergence | unproven | partial then flat | regressed after first denial |
| Completion judgment | poor | poor | poor |
| Hook/evidence transport | worked | worked | worked with complete per-attempt snapshots |

Task-05 is not better convergence than Task-04. It is worse: after a valid narrow first fix, deterministic feedback causes a regression into a broken/incomparable state that persists to the bound.

Task-05 is cleaner evidence than Task-03 because there is no pager confounder and every validation attempt survives. It therefore strengthens, rather than weakens, the attribution toward model strategy/evidence interpretation under this task/model configuration.

## Behavioral ratings

| Dimension | Rating | Evidence |
| --- | --- | --- |
| Investigation quality | MIXED | reads POMs, runs scanner/builds/SBOM/tree, eventually checks Central directly; does not organize remaining findings by compatible dependency family |
| Tool choice | POOR | saves 404 HTML as .pom, repeatedly deletes Maven caches, 48 Maven build invocations, broad POM churn |
| Evidence acquisition | GOOD/MIXED | obtains authoritative hook evidence, valid builds, SBOM scan, dependency tree and Central 404; initial direct OSV invocation is incomplete |
| Evidence interpretation | POOR | empty incomplete scan treated as success; 404 treated as environment issue; dependency-tree Jackson 3 evidence followed by Boot downgrade |
| Strategy selection | POOR | immediate forbidden 4.0.6 -> 3.2.5 downgrade after denial 1; later 2.7.18 |
| Reassessment after feedback | POOR/MIXED | temporary restorations occur, but rejected downgrade is repeatedly reintroduced |
| Recovery from failed approaches | POOR | no durable escape from nonexistent artifact strategy despite direct 404 evidence |
| Constraint adherence | POOR | Boot downgrade; Java configuration changed; nonminimal broad POM edits |
| Self-validation | POOR | repeated builds, but initial scanner failure is ignored and later valid scan evidence is not reconciled |
| Completion judgment | POOR | completion attempted after incomplete self-scan and later after known build/security/policy failures |
| Final outcome | POOR | BOUNDED_FAIL, build broken, scan incomplete, 25 UNKNOWN, policy failures |

## Harness and architecture attribution

### Proven working in Task-05

- staged Startup -> Verify -> Execute orchestration;
- automatic task numbering;
- clean deterministic baseline;
- Vertex/OpenHands runtime;
- repository editing and terminal tools;
- Maven access;
- OSV access;
- native Stop Hook interception;
- same-conversation continuation;
- decision-critical validator feedback;
- per-attempt validation snapshots;
- observable event persistence;
- automatic evidence publication.

### Not proven as a harness capability gap

No new missing retry/planner/memory/browser capability is demonstrated.

The agent had:

- exact remaining finding identities/current versions from the hook;
- Maven build capability;
- Maven Central access;
- curl;
- dependency tree;
- SBOM generation;
- OSV Scanner;
- a working Boot 4.0.6 build state after denial 3.

The failure persists despite those capabilities.

### Tool/prompt friction worth recording

The agent-visible raw OSV invocation does not automatically reproduce the deterministic validator's Maven-aware local-repository staging. The task contract correctly says that baseline/independent validation use Maven-aware local repository support, but it does not prescribe the wrapper command to the agent.

That is a real evidence-acquisition friction point, but it does not explain the whole run: after denial 3 the agent successfully generates an SBOM and obtains a broad OSV vulnerability report, and still returns to the rejected downgrade strategy.

Therefore this friction should not be converted into a custom remediation workflow or recipe.

## Evidence-capture assessment

The new capture design is sufficient for Task-05 trajectory analysis:

- all 407 observable events persisted;
- all four full validation attempts persisted;
- final validation persisted;
- startup/verify/execute/combined logs persisted;
- baseline and final Git state/diff persisted.

Two metadata defects are visible but nonblocking:

1. generated evidence `README.md` contains blank interpolated run/task/stage fields;
2. `run-metadata.txt` has blank Vertex project/location because those exports occurred only in child setup processes rather than the parent orchestrator.

These do not invalidate Task-05 because the task id, branch, conversation, model, validation reports, and runtime logs are independently recoverable.

**Post-run fix:** commit `c67b6e2ece41fee650a93a035ef3337a0d3e80a9` corrects both audit-only defects by resolving the shared Vertex environment in the orchestrator itself and by using shell-safe `printf` formats for the Markdown evidence README. This does not change the model, task prompt, validator, Stop Hook semantics, or remediation behavior.

## External research findings relevant to attribution

### Spring Boot 3 vs 4 starter coordinate

Official Spring Boot 3.2.5 documentation uses `spring-boot-starter-web` for Spring MVC applications. Spring's Boot 4 modularization announcement explicitly explains that the Boot 3 `web` starter was renamed to `webmvc` in Boot 4. Current Boot 4 documentation uses `spring-boot-starter-webmvc`.

That independently confirms the Task-05 inference from Maven Central's 404: `spring-boot-starter-webmvc:3.2.5` is a cross-major coordinate mismatch created by the downgrade, not evidence of a general network/proxy outage.

### OSV Scanner Maven resolution

Current OSV-Scanner documentation states that Maven POM scanning resolves transitive dependencies and supports native Maven registry resolution with `--data-source=native` and `--maven-registry=<URL>`. Its issue tracker also contains recent reports about local Maven-module/cache resolution limitations.

This matches Task-05's observed difference between the agent's simple recursive scan and the deterministic validator's Maven-aware local-registry setup. The important failure is that the agent ignored the scanner's explicit local-module resolution errors and accepted an empty JSON result as security success.

### OpenHands stuck detection

Current OpenHands SDK source documents native stuck detection for recent repeating action/observation cycles, action/error cycles, repeated monologue, alternating patterns, and context-window errors. The detector works over a bounded recent-event window.

Task-05 contains strategic repetition but many syntactically different POM edits and build attempts. Therefore this run does not prove the native stuck detector is broken; it shows that pattern-level repetition detection does not guarantee higher-level strategy reassessment.

These external findings reinforce the architecture attribution already made above: no new generic harness capability gap is proven by Task-05.

## Decision and next step

**CONTINUE EVALUATION, but do not add more OpenHands-specific planning/retry/memory/remediation guidance.**

Task-05 strengthens the conclusion from Task-04:

- native OpenHands completion control and evidence transport are working;
- deterministic validation is working;
- the remaining dominant problem is the tested model/agent's engineering judgment, evidence interpretation, strategy correction, and completion judgment.

Because the company Vertex environment currently exposes only Gemini 2.5 Flash for this POC, stronger-model isolation remains blocked.

The next meaningful platform experiment is therefore a fair comparison against the planned alternative harness under the same repository, task contract, Gemini model, Vertex path, and deterministic validator, after fixing only the nonbehavioral evidence-metadata defects. Do not change the remediation prompt or add solution hints before that comparison.
