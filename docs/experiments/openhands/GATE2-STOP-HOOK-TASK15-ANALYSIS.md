# Task-15 consolidated engineering evaluation and stability-replication baseline

Status: **FINAL READ-ONLY ASSESSMENT — CONTINUE EVALUATION**. Reviewed 2026-10-10/11. No runtime, prompt, Skill, validator, target remediation or harness changes are authorized by this assessment.

## Identity, configuration and evidence

- Control repository/branch: `AILearner365/oss-remediation-adk` / `openhands-poc-evaluation`; control head recorded in run metadata: `26868cf132b9dc88d166d094140155310149be56`.
- Target baseline: `AILearner365/maven-multimodule-app`, `main-runrunning`, commit `9ea1b0ed5ca255db0fc7c659d050896d3ed5db78`.
- Task: 15; evidence: [orchestrated run 20261011T010954Z](evidence/gate2-orchestrated-run-20261011T010954Z/README.md), [128-event trajectory](evidence/gate2-orchestrated-run-20261011T010954Z/trajectory-dd9a51578b224d19aa090189c5c5a445/events.jsonl), [baseline](evidence/gate2-orchestrated-run-20261011T010954Z/baseline.json), [validation](evidence/gate2-orchestrated-run-20261011T010954Z/validation.json), [final diff](evidence/gate2-orchestrated-run-20261011T010954Z/final.diff), [Git state](evidence/gate2-orchestrated-run-20261011T010954Z/git-state.txt), [metadata](evidence/gate2-orchestrated-run-20261011T010954Z/run-metadata.txt).
- Model: `vertex_ai/gemini-2.5-flash`; pinned SDK/tools baseline: OpenHands 1.50.0. `max_denials=3`, `max_iterations=250`. Recorded flags: `engineering_judgment_guidance=0`, `structured_guidance=1`, `task_skill=0`. A `maven-dependency-evidence` Skill was **actually invoked** at E24; do not conflate the task_skill flag with observable invocation or assume causal benefit. Exact provider thinking budget/grounding and token/cost metrics are not established by the published event projection.
- Source of truth for criteria: [ENGINEERING-EVALUATION-SCORECARD.md](ENGINEERING-EVALUATION-SCORECARD.md). This is an evaluation record, not a new nine-gate runtime policy.

## Separate outcomes

**Deterministic: PASS.** The independent validator reports 26/26 original HIGH/CRITICAL findings resolved, zero remaining/unknown, zero prohibited new findings, passing Maven build/tests/startup and recorded constraints. One validation attempt, exit code 0.

**Engineering acceptance: NOT PROVEN.** The resulting POM passes the defined contract, but six individually managed dependency overrides have not been shown to be the smallest necessary, mutually release-family-aligned solution. A passing scan and limited build/test suite cannot establish all downstream compatibility or maintainability.

**Reasoning: MIXED; efficiency: POOR; platform decision: CONTINUE EVALUATION.** Do not promote the target patch merely because the Stop Hook allowed completion.

## Observable decision audit

| Event(s) | Decision / observation | Evidence and assessment |
| --- | --- | --- |
| E4-E8 | Initial attempt to pass Maven `dependency:tree` text as OSV SBOM failed; agent checked scanner help and corrected to `osv-scanner scan source`. | Good tool-error recovery; initial format assumption unverified. |
| E16-E18 | Inspected Jackson databind resolution; moved Spring Boot parent 4.0.6 to 4.0.7. | **First consequential version-selection gap**: no observed authoritative 4.0.7-versus-4.0.8 comparison before edit. Incremental patch-line choice is plausible, not justified as best choice. |
| E24-E27 | Invoked `maven-dependency-evidence`; ran Maven Versions Plugin `display-parent-updates`. | Capability was available and used, but after the initial Boot commitment. Configured, delivered, invoked, used and effective must be evaluated separately. |
| E28-E39 | Jackson edits and a malformed-POM failure at E33, followed by undo/reinsert and successful build E39. | Recovery succeeded; editing/build churn was avoidable in principle. |
| E44-E65 | Direct JSON edit, Jackson core inspection, repeated insertion/undo, dependency-resolution failures E51/E57, eventual successful build E65. | Iterative correction, but poor evidence yield per edit/build; do not invent exact minimum number of necessary actions. |
| E70-E77 | Further direct dependency changes, Boot parent 4.0.7 and repeated build/scan. | No documented comprehensive candidate comparison before continuing. |
| E80-E85 | Dependency-tree inspection including `spring-webflux` query without a matching dependency line, then WebFlux management override. | Override scope is not adequately supported by observed resolved-graph evidence; no claim that it is definitely harmful or absent from every graph is warranted. |
| E87-E105 | More successful builds/scans, WebMVC/Log4j changes and dependency-tree checks. | Useful incremental feedback mixed with trial-and-error accumulation of overrides. |
| E107-E120 | Changed parent to 4.0.8; built and scanned; added Tomcat core override; final build/scan and independent validator PASS. | 4.0.8 was a credible patch-line candidate but was considered late. The evidence proves the final **combination** passed, not that every override was required. |
| Final | Agent claimed complete remediation. | Supported within deterministic contract; broader production engineering acceptance remains unproven. |

**Why 4.0.7 then 4.0.8?** The observable record shows successive candidate edits and feedback-driven progression, not an explicit pre-edit ranking of 4.0.7 against 4.0.8. Do not claim to know private chain-of-thought or a hidden rationale. A credible alternative was to test the Spring Boot 4.0.8 managed dependency set first, then add only evidence-necessary overrides; this is **untested**, not a proven better patch.

**Final tracked patch:** `pom.xml` parent 4.0.6 -> 4.0.8; dependency management for `tools.jackson.core:jackson-databind:3.1.7`, `tools.jackson.core:jackson-core:3.1.7`, `org.apache.logging.log4j:log4j-api:2.25.5`, `org.springframework:spring-webmvc:7.0.9`, `org.springframework:spring-webflux:7.0.9`, `org.apache.tomcat.embed:tomcat-embed-core:11.0.25`; direct `org.apache.commons:commons-text:1.9 -> 1.10.0` and `org.json:json:20230227 -> 20231013`. Jackson core/databind are aligned with each other, but full Jackson/Tomcat/Log4j/Spring family alignment and necessity relative to the 4.0.8 BOM were **not proven**. No override is designated for removal without further evidence.

**Delivery-hygiene gap:** [Git state](evidence/gate2-orchestrated-run-20261011T010954Z/git-state.txt) shows only `pom.xml` tracked modified, plus untracked `dependencies.txt` and eight `osv-scan-report*.json` files. The validator reported ten changed files but passed its delivery-diff hygiene check. This is a reproducible *coverage gap in the existing check*, not evidence that those files were committed or delivered. Separate harness responsibility from model strategy.

## Nine-dimension scorecard

Qualitative rating and evidence confidence are independent. Event identifiers refer to the exported Task-15 trajectory.

| Dimension | Rating | Confidence | Evidence-backed conclusion |
| --- | --- | --- | --- |
| 1. Guidance effectiveness | MIXED | PARTIAL | Structured guidance configured; Skill invoked E24; no controlled causal attribution, and exact model-use of each instruction not provable. |
| 2. Evidence-driven reassessment | GOOD | PARTIAL | Corrected scanner usage E4-E8, POM error E33-E39, dependency failures E51-E65, and ultimately revised Boot to 4.0.8 E107. |
| 3. Technical correctness | MIXED | PARTIAL | Independent 26/26, build/test/startup PASS; full dependency-family compatibility and production coverage unresolved. |
| 4. Unsupported strategy selection | MIXED | PARTIAL | E18 Boot 4.0.7 before authoritative parent discovery; overrides added without demonstrated coherent-BOM comparison. |
| 5. Strategy fixation | GOOD | PARTIAL | No observed forbidden Boot 3 downgrade; meaningful corrections, though some repeat-edit churn. |
| 6. Preservation of progress | MIXED | PARTIAL | Retained final valid patch, but intermediate POM and dependency-resolution regressions and repeated edit/undo cycles. |
| 7. Stale or inaccurate knowledge | UNRESOLVED | UNRESOLVED | No basis to attribute choices to training staleness; invalid tool-format assumption and version-verification gaps are observable. |
| 8. Solution quality | MIXED | PARTIAL | Accepted security outcome, but six overrides may be redundant or misaligned; minimality/downstream impact not proven. |
| 9. Performance and efficiency | POOR | PARTIAL | 128 exported events, 61 actions, 31 FileEditorActions, 11 `mvn clean install`, eight source scans, about 14m06s. Avoidable churn observed; exact minimum/cost not established. |

### Recovery and case-specific checks

- **Missing artifact vs repository outage:** dependency-resolution errors observed, but no sufficient basis to claim an indiscriminate Maven Central outage or shared-cache deletion. Do not score absent evidence as proven good behavior.
- **Destructive shared-cache cleanup:** no destructive cache-cleanup action identified in the reviewed actions; mark NOT EXERCISED for that case.
- **Spring Boot constraints:** final 4.0.8 is not a downgrade; forbidden Boot 3 strategy seen in prior runs was not repeated.
- **Incomplete remediation claim:** final independent validation passed original-finding reconciliation; no unsupported premature completion shown in this run.
- **Recovery quality:** tool errors were corrected, but the Jackson/POM edit cycles and repeated full builds demonstrate efficiency weaknesses.

## Historical context and confounders

- Task-05: BOUNDED_FAIL; 407 events, 48 agent Maven installs; repeated Boot downgrade and strategy fixation.
- Task-06: DETERMINISTIC PASS; 255 events, 15 agent Maven installs; later recovery but initially unsupported downgrade, partial-family overrides and leftover reports.
- Task-07: BOUNDED_FAIL; recurring unsupported Boot assumptions and incomplete remediation.
- Task-15: DETERMINISTIC PASS; 128 events, 11 agent Maven installs, eight scans; no observed forbidden downgrade, but unsupported early version selection, patch-minimality concern and workspace artifacts.

The lower counts and stronger completion are **descriptive**, not proof that structured guidance, Skills, OpenHands, or the model improved causally. Historical advisory counts differed (Task-05 25 vs Task-06 26), and guidance/configuration, random model sampling and possibly external package/advisory availability are confounders. Do not compare cost without comparable cost capture. Published trajectory excludes internal model reasoning and raw provider responses.

## Final priority diagnosis and responsibility split

1. **P1: Pre-commitment evidence quality (model/agent behavior).** Repeated weak initial choices across runs; verify consequential version/release/constraint assumptions before edits.
2. **P2: Best-supported, minimal and compatible strategy (model/agent behavior).** Compare meaningful credible alternatives when warranted; reason about BOM/release-family, upstream/downstream impacts and necessity of overrides. Do not force arbitrary multiple alternatives or a recipe.
3. **P3: Evidence yield and efficiency (model/agent behavior).** Distinguish purposeful hypothesis tests from repeated edit/build/scan cycles that do not resolve a new uncertainty.
4. **P4: Delivery artifact hygiene (deterministic harness).** Existing check misses untracked investigation files; treat separately from engineering judgment.

These are **prioritized observations, not authorized implementation tasks**. Do not add a critic, planner, custom patch DSL, additional agent, prescriptive dependency versions, prompt, Skill, model change, validator change, or orchestration change now. Stronger-model isolation remains unavailable under recorded Vertex access; do not attribute weaknesses uniquely to the model or harness.

## Agreed next experiment: unchanged stability replication

**Freeze this Task-15 assessment and run one clean trial with unchanged effective controls.** Use the existing [orchestrated runbook](GATE2-ORCHESTRATED-RUNBOOK.md). The orchestrator automatically chooses the next unused numeric task id; do not reuse Task-15 state or remediation edits. Capture and verify: control commit and guidance/Skill hashes, task-contract hash, model/SDK/tools, baseline commit, advisory identities, scanner/validator, Stop Hook, bounds, and all relevant flags. If any differ materially, record the confounder rather than labeling the run controlled.

Compare Task-15 vs replication on **first consequential strategy and authoritative evidence available before it; 4.0.7/4.0.8 or other version rationale; credible alternatives; dependency-family alignment and patch minimality; contrary evidence and time/actions to revision; preservation of healthy states; tool/build/scan evidence yield; errors and recovery; original-finding reconciliation; untracked artifacts; elapsed time and available tokens/cost**. Apply the same nine dimensions and event-linked audit, keeping deterministic PASS, engineering acceptance and reasoning confidence separate.

**Decision after replication:** classify findings as recurring, variable or confounded, then select at most one narrowly evidenced intervention, or continue unchanged. A single replication does not establish statistical stability. No further narrow read-only investigation is a prerequisite to the next run.

**Platform verdict:** CONTINUE EVALUATION; OpenHands harness mechanics and deterministic completion are demonstrated, but consistently strong and efficient autonomous engineering is NOT PROVEN. No repository target patch delivery is authorized by this assessment.
