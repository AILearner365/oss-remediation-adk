# Task-14 harness review and offline replay

**Status:** focused harness corrections complete; no Task-15 or replacement remediation run performed. Historical evidence under `evidence/gate2-orchestrated-run-20261010T232329Z/` is unchanged.

## Confirmed findings

Task-14's recorded result remains a deterministic failure: 20 of 26 original HIGH/CRITICAL findings resolved, six remaining, with build/tests passing after four validation attempts. The historical validator reports are not relabeled by this review.

- **Suppression false positive — confirmed root cause.** `ConstraintEvaluator` searched every added diff line for suppression-like words without tracking the changed path. Advisory description prose in generated `osv-output.json` therefore matched even though no supported suppression configuration changed. The classifier now limits content inspection to known scanner-suppression files and Maven `pom.xml` suppression/exclusion constructs. Hash comparison for the historically supported OSV configuration files remains intact.
- **Spring Boot false rejection — confirmed root cause.** The configured contract is `version_policies.spring_boot`, and its fields constrain patch/minor/major/downgrade movement, not declaration layout. The implementation compared declaration-source cardinality, so adding a same-version property/BOM beside the unchanged parent produced `configuration_changed`. Capture now records controlling Spring Boot parent and imported BOM declarations, resolves local Maven properties, compares their effective version set, and rejects conflicting parent/BOM sets. Task-14's Maven-generated effective POM and successful build both show Boot 4.0.6; the recorded diff adds a 4.0.6 BOM controlled by `spring-boot.version=4.0.6` while retaining parent 4.0.6.
- **Engineering-judgment guidance — configured, available and delivered in Task-14.** The fresh-run script passes its environment unchanged to the execution script; that script supplies no guidance CLI override. The runner log records `ENGINEERING_JUDGMENT_GUIDANCE=.../engineering-judgment.md`, and the rendered system prompt contains the exact guidance text. This proves the effective `OPENHANDS_ENGINEERING_JUDGMENT_GUIDANCE=1` path, not behavioral compliance or causal benefit.
- **Maven Skill — present in the control checkout but not configured, available, or delivered to the Task-14 agent.** Task-14 logged only the mutually exclusive legacy guidance mode; it did not log `GENERAL_GUIDANCE`, `REPOSITORY_GUIDANCE`, or `MAVEN_SKILL`, and the exported trajectory contains no Maven Skill activation/body evidence. Maven commands do not prove Skill use. The structured-guidance path is independently covered offline, and future runs now emit a machine-readable configured/available/delivered record plus source hashes. Task-14 observed use remains **NOT PROVEN**.

The recorded missing-artifact attribution, shared Maven-cache deletion, repeated completion attempts, completion claim with six findings remaining, and uneven recovery are observable agent behaviors. Their private cause is unresolved. The stop hook correctly rejected failed completion attempts and ultimately returned the bounded failure defined by the existing denial policy; this review does not reinterpret that behavior as successful remediation.

## Changes

- `autonomous_oss_remediation_agent/deterministic/constraints.py`: path-aware suppression classification; Maven parent/BOM effective-version comparison; incompatible-combination detection; declaration evidence retained for audit.
- `tests/unit/test_autonomous_scanner_constraints.py`: generated-output and exact Task-14-diff false-positive replays, plus real POM exclusion coverage.
- `tests/unit/test_autonomous_spring_boot_policy.py`: same-version property/BOM and incompatible parent/BOM regressions; prerelease fail-closed expectation aligned with the existing classifier.
- `scripts/openhands/openhands-gate2-stop-hook-run.py`: emits guidance/Skill configuration, availability, trigger delivery, hashes, and an explicit `observedUsed=NOT_PROVEN` boundary.
- `scripts/openhands/openhands-gate2-fresh-run.sh`: records all three guidance switches and hashes of guidance/Skill inputs in future run metadata.
- `ENGINEERING-EVALUATION-SCORECARD.md`: adds Task-14's five behavioral cases as reusable, technology-neutral evaluation criteria.
- Project memory records the decision, results, limits, and return point.

## Offline verification and replay

These are new offline outcomes, separate from the recorded Task-14 validation outcomes:

| Check | Offline result |
| --- | --- |
| Constraint/policy focused suite | 41 passed, 1 Windows-only skipped, 11 subtests passed |
| Pinned OpenHands 1.50.0 guidance suite | 6 passed |
| Exact recorded `final.diff` suppression replay | PASS; no changed suppression file and no supported added suppression line |
| Task-14 baseline + retained final workspace Spring replay | PASS; baseline 4.0.6, final effective set 4.0.6, declarations `parent=4.0.6` and `bom=4.0.6` |
| Genuine suppression/exclusion regressions | PASS; OSV/Dependency-Check suppression-file changes and added POM exclusions are rejected |
| Major/downgrade/prerelease/incompatible Boot regressions | PASS; all remain rejected unless the existing policy explicitly permits the applicable movement |

One combined dependency environment was unsuitable because the pinned OpenHands packages conflicted with the repository's installed Google ADK/GenAI versions during test collection. The two intended pinned environments were therefore run separately; both focused suites passed. This is a test-environment dependency conflict, not a Task-14 runtime outcome.

No live agent, scanner, authentication acceptance test, Task-15 run, or new remediation trial was executed.

## Acceptance

| Item | Status | Basis |
| --- | --- | --- |
| Suppression false positive | **PROVEN** | Exact recorded diff now passes and generated JSON is outside supported policy inputs. |
| Genuine suppression detection | **PROVEN** | Known suppression files and POM exclusions fail focused regressions. |
| Spring Boot policy correctness | **PROVEN** | Same effective 4.0.6 passes; downgrade, major, prerelease and conflicting parent/BOM cases remain covered. |
| Engineering-judgment guidance delivery | **PROVEN** | Task-14 log path plus exact rendered system context; future structured evidence added. |
| Maven Skill availability | **PARTIAL** | Offline configured path loads/advertises/triggers it; Task-14 did not configure it. |
| Maven Skill observed usage | **NOT PROVEN** | No Task-14 activation/read/use evidence; Maven commands are not credited. |
| Behavioral regression coverage | **PROVEN** | Five reusable evaluation cases are now part of the adopted scorecard. |
| Existing harness behavior preserved | **PARTIAL** | Focused offline suites pass and policies remain fail-closed; no broad or live run was authorized. |

## Remaining gaps

- Future runtime logs can prove Skill delivery, but whether an agent used delivered guidance still requires trajectory evidence and behavioral review.
- Task-14 does not establish why the agent ignored delivered engineering guidance, generalized artifact-specific failures, or chose destructive cache cleanup.
- The effective-version classifier covers Spring Boot parent and imported Boot BOM control points represented in Maven POMs. It does not claim a full general-purpose Maven model implementation.
- No new evidence changes the six unresolved Task-14 findings or establishes a successful remediation outcome.
