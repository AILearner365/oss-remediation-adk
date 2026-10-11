# Gate 2 Task-15 vs Task-16: stability and engineering-reasoning assessment

Status: **CONSOLIDATED VALIDATOR + COMPLETE EXPORTED EVENT-LEVEL COMPARISON**. 2026-10-11. Review only; no agent, guidance, Skill, runtime or validator changes made.

## Verdict

**Task-16 was an actual controlled-configuration replication that failed, not an ADC failure.** The earlier Task-16 startup failure (`20261011T031548Z`, `stage=STARTUP`) is a separate record, with `structured_guidance=0`. The later actual trial (`20261011T033535Z`, Task-16) has the intended `engineering_judgment_guidance=0`, `task_skill=0`, `structured_guidance=1`; model `vertex_ai/gemini-2.5-flash`; `max_denials=3`; `max_iterations=250`. Recorded hashes of guidance/context/Skills match Task-15. Target baseline Git SHA `9ea1b0ed5ca255db0fc7c659d050896d3ed5db78` matches Task-15. Control head differs because the evaluation review and failed-startup evidence were subsequently committed; review these for any change to agent-consumed content, rather than treating the mere control SHA change as an effective configuration change.

**Task-15 deterministic PASS; Task-16 deterministic BOUNDED_FAIL.** Replication therefore does **not** establish stable autonomous remediation. Strongest recurring problem is unsupported strategy/constraint management; newly decisive Task-16 failure is loss of scan coverage after editing dependency declarations. The validator correctly blocked false success.

## Evidence pointers and limitations

- [Task-15 baseline assessment](GATE2-STOP-HOOK-TASK15-ANALYSIS.md) and [Task-15 run](evidence/gate2-orchestrated-run-20261011T010954Z/README.md).
- [Task-16 run](evidence/gate2-orchestrated-run-20261011T033535Z/README.md); [metadata](evidence/gate2-orchestrated-run-20261011T033535Z/run-metadata.txt); [final diff](evidence/gate2-orchestrated-run-20261011T033535Z/final.diff); [Git state](evidence/gate2-orchestrated-run-20261011T033535Z/git-state.txt); [validation 1](evidence/gate2-orchestrated-run-20261011T033535Z/validation-attempt-1.json), [validation 2](evidence/gate2-orchestrated-run-20261011T033535Z/validation-attempt-2.json), [validation 3](evidence/gate2-orchestrated-run-20261011T033535Z/validation-attempt-3.json), [validation 4](evidence/gate2-orchestrated-run-20261011T033535Z/validation-attempt-4.json); [event trajectory](evidence/gate2-orchestrated-run-20261011T033535Z/trajectory-0955955ec6de48c1a53bb4e46e9d1ee1/events.jsonl).
- **Full event-level follow-up (2026-10-11):** The GitHub Git-blob reader successfully returned the complete published `events.jsonl` despite earlier contents-reader size limitations. All 273 observable events have now been parsed: 128 ActionEvents, 128 ObservationEvents, seven MessageEvents, four HookExecutionEvents, five Condensation markers, and one SystemPromptEvent. The manifest/export explicitly omits private reasoning, some context and raw provider fields, so causal model intent remains unobservable. See event-level diagnosis below.

## Validation checkpoints (independently verified)

| Measure | Task-15 final | Task-16 Stop Hook #1 | Task-16 #2 | Task-16 #3 | Task-16 #4 final |
| --- | --- | --- | --- | --- | --- |
| Overall | PASS | FAIL | FAIL | FAIL | FAIL |
| Baseline original HIGH/CRITICAL | 26 | 26 | 26 | 26 | 26 |
| Proven resolved | 26 | 2 | 12 | 0 verifiable | 0 verifiable |
| Remaining | 0 | 24 | 14 | unknown | unknown |
| Unknown original findings | 0 | 0 | 0 | 26 | 26 |
| Scannable packages baseline | 10 | 10 | 10 | 10 | 10 |
| Scannable packages current | 10 | 10 | 10 | **0** | **0** |
| Spring Boot parent | 4.0.8 | 4.0.6 | **3.3.1** | 4.0.7 | 4.0.7 |
| Maven build/test/startup | PASS | PASS | PASS | PASS | PASS |
| No new prohibited findings | PASS | PASS | FAIL (30 reported) | Inconclusive | Inconclusive |
| Key issue | Further engineering quality unproven | Incomplete remediation | Forbidden downgrade and 30 new findings | Coverage collapse | Coverage collapse not repaired |

Attempt 3 and 4 OSV backend outcome `COMPLETED_CLEAN` means **no findings among scanned packages**, *not* a valid clean equivalent scan. Package extraction fell from 16 to 6; all six extracted packages were filtered as unscannable. Independent target reconciliation explicitly returned comparison incomplete and 26 unknown. The `no_new_prohibited_findings` checkpoint says scan comparison unavailable despite backend success; do not mislabel it as complete.

Task-16 #1 also flagged a likely investigation artifact; by final Git state there were three untracked artifacts (`json-smart-updates.txt`, `osv-scan-report.json`, `osv-scan-root-pom.json`) and only `pom.xml` tracked modified. The final delivery-diff-hygiene check PASSED despite these remaining untracked files. This is a scope/coverage inconsistency for the hygiene check, separate from the security failure; not proof untracked files would enter a commit.

## Final POM diff and the direct dependency/management boundary

Task-16 final tracked patch (only `pom.xml`): Boot parent `4.0.6 -> 4.0.7`; remove top-level `<dependencies>` containing direct `commons-text:1.9` and `json:20230227`; introduce inside `<dependencyManagement><dependencies>` `commons-text:1.12.0`, `json:20231013`, and `commons-lang3:3.18.0`. The final diff does not show corresponding direct dependencies reintroduced. **Dependency management sets versions but does not itself put an artifact on a Maven dependency graph.** That is a supported explanation for the package-coverage collapse; the actual precise scan extraction cause is not uniquely established without comparing effective dependency trees and scanner extraction logs. The validator proves coverage loss regardless of cause.

The attempt-2 `task-web/pom.xml` modification present in that checkpoint is absent from final tracked diff; a provisional change was not preserved. The temporal checkpoints show the agent returned from forbidden Boot 3.3.1 to 4.0.7 by attempt 3 but did **not** restore scannable package coverage by attempt 4. The agent's rationale for the fallback or its treatment of validator messages is unavailable without reading the event bodies.

## Comparable engineering observations

1. **Outcome reliability: NOT PROVEN / observed instability.** Task-15 and Task-16 ran the same target baseline and intended guidance/control bounds but ended PASS and FAIL. Two runs cannot assign a statistically reliable probability; environmental changes, Maven metadata and advisory conditions may confound.
2. **Strategy selection/constraint handling: recurring weakness.** Task-15 selected Boot 4.0.7 before trying 4.0.8, lacked pre-commitment BOM/patch-line comparison; Task-16 temporarily downgraded to forbidden 3.3.1. The Boot 3 violation was corrected after Stop Hook feedback, but it consumed a denial and generated 30 new prohibited findings.
3. **Goal preservation/dependency reasoning: critical new failure.** Task-16 ultimately satisfied Maven build/test/startup but made the security measurement impossible by removing declared direct dependencies from active graph. This is not successful remediation just because scan said clean. Security-goal and scanner-evidence invariants were not sustained across strategy changes.
4. **Recovery: PARTIAL / final failure.** Intermediate improvement (2->12 resolved) and Boot policy repair (3.3.1->4.0.7) show some correction. Recovery did not address validation's zero scannable packages and unknown 26 findings by the final allowed attempt. Exact cause (misreading, ignoring, inadequate feedback specificity, approach fixation) is not inferable from checkpoints alone.
5. **Solution quality: unacceptable for Task-16.** Final patch cannot be accepted on security effectiveness or engineering correctness, irrespective of successful Maven build and no suppression changes. Task-15's 26/26 resolution was better but its six overrides' minimality and family compatibility were not proven.
6. **Efficiency: Task-16 worse on observable gross proxies.** Task-15 128 exported events, one validation attempt, ~14m06s. Task-16 273 exported events, four validator attempts and three denied completions; run began 03:35:35Z and finished approximately 04:06:49Z based on operator output (~31m). These counts aren't identical to edit/build/scan counts; no verified direct Task-16 action-count breakdown or time/cost normalization. Terminal displays 11.32M cumulative input tokens and 71.94K cumulative output tokens, but the exported trace omits provider stats and model-call detail, so don't claim a comparable billing measurement.
7. **Harness: deterministic safety boundary did its job.** Stop Hook refused downgrade and coverage-hole false success, preserved multiple validation attempts, and terminated after the configured denial budget. The event UI warning about missing visualization mapping for `HookExecutionEvent` is a presentation issue; it does not explain the deterministic failure.

## Nine-dimension comparative scoring

These are qualitative evidence-backed judgments, not hidden model reasoning. Confidence remains separate from score.

| Dimension | Task-15 frozen | Task-16 | Task-16 confidence |
| --- | --- | --- | --- |
| Guidance effectiveness | MIXED | INCONCLUSIVE: flags match, failure occurred, causal use unverified | PARTIAL |
| Evidence-driven reassessment | GOOD | MIXED: policy was repaired, security coverage wasn't | PARTIAL |
| Technical correctness | MIXED | POOR: final target comparison impossible | HIGH for validator fact |
| Unsupported strategy selection | MIXED | POOR: Boot 3.3.1 downgrade, non-resolving management relocation | HIGH for results, PARTIAL for attribution |
| Strategy fixation | GOOD | MIXED: Boot downgrade corrected; coverage-hole remained | PARTIAL |
| Preservation of progress | MIXED | POOR: initial 12/26 provable resolutions became 26 unknown | HIGH for checkpoint effects |
| Stale/inaccurate knowledge | UNRESOLVED | UNRESOLVED: cannot identify model training staleness | UNRESOLVED |
| Solution quality | MIXED | POOR: non-acceptable dependency result | HIGH for validator fact |
| Performance/efficiency | POOR | POOR: 273 events, four validation attempts, no accepted outcome | PARTIAL |

## Highest-value intervention: decision, not implementation

**Do not rerun unchanged immediately. Do not increase denial budget, relax scan coverage, hard-code versions, or add a separate planner/critic.** An unchanged run could pass or fail again without resolving why scan coverage was lost.

**Recommend one narrow, generalizable reasoning-contract intervention after extracting the readable event timeline:** reinforce *goal preservation and decision-critical evidence* at the model-owned investigation/implementation boundary. Before treating a dependency edit as security remediation, require reasoning from the actual effective/transitive dependency graph and credible scanner coverage; `dependencyManagement` alone does not ensure a dependency is active. When feedback says the measured target universe is unknown or shrank, the agent must treat it as incomplete evidence, investigate and correct, rather than treat a clean scan as success. Constraint checking should prevent forbidden major-version downgrades before editing. This must be expressed as technology-neutral success/evidence principles wherever possible, not a new Maven remediation recipe, mandated fixed workflow, dependency version, forced extra alternatives or harness-controlled engineering plan. Whether the *right actual fix* is better existing-feedback delivery, scoped guidance wording, or tracing/instrumentation needs event-level proof first.

**Deterministic harness follow-up (separate priority):** the coverage gate already works and should stay enforced. Investigate why final untracked reports pass hygiene, but do not combine unrelated cleanup into the first reasoning intervention.

**Next action:** publish or locally summarize the 273 events into compact event-id/action/observation/Stop-Hook-feedback sequence, then make exactly one bounded change based on that evidence and test against both failure mode and no-regression criteria. No new live run until that change and evaluation design are settled. Existing evidence supports this choice without any additional build.

## Full observable event-level diagnosis: ignored, misunderstood, or under-guided?

**Primary diagnosis: model-owned judgment and feedback-use failure, not absence of Stop Hook feedback.** This conclusion is based on observable output/actions, not private thought. The task prompt expressly banned Spring Boot downgrades and required *all* HIGH/CRITICAL findings resolved with scanner evidence; it also directed use of the Maven Skill when published-version facts materially matter and warned that incomplete scans are not clean.

**Four phases (event indices are zero-based JSONL positions):**

1. **Premature completion, E2–E30.** The agent scanned, built and edited just direct `commons-text`/`json` versions (E16/E18), then declared success in E28, describing only **two** vulnerabilities despite baseline **26**. Stop Hook E29 supplied concrete remaining identities: 24/26 remained, plus `dependency-tree.txt` hygiene failure. Feedback was delivered back as an environment user message E30.
2. **Misinterpreted forbidden downgrade, E31–E75.** Directly after feedback, the agent changed Boot **4.0.6 -> 3.3.1** (E33), then repaired broken starter resolution and changed the web starter. Its E73 answer explicitly rationalized `3.3.1` as a permissible minor upgrade because `4.0.6` seemed “non-standard.” This proves an incorrect interpretation of a *clear* constraint, not insufficient policy wording. Hook E74 responded clearly: `spring_boot_version_policy` downgrade, 14 targets remain, 30 new prohibited findings; delivered again as message E75.
3. **Partial correction, then disappearance of security coverage, E76–E190.** E85 restored Boot 4.0.6, later E152 moved it to 4.0.7. It experimented with numerous override families and builds. Crucially, E160 **removed direct commons-text dependency**, E166 **removed the remaining root direct dependencies section containing JSON**, and E168 inserted JSON only into dependencyManagement, with managed commons-text already present. Later source scan E183/E184 showed **0 packages** extracted from root POM, six local/unscannable total; E186 had `results: []`. Nevertheless agent E187 attempted to finish claiming all HIGH/CRITICAL resolved. Hook E189 clearly stated scannable-package coverage below baseline, absent findings UNKNOWN, earlier progress regressed; message E190 delivered it. Independent validator: 10 scannable baseline -> **zero**; 26 original findings **UNKNOWN**, not resolved.
4. **Post-feedback recovery diverged and failed, E191–E272.** Immediately after E190 (coverage failure), E191 changed Boot **4.0.7 -> 3.2.11**, another forbidden downgrade, later reverted at E205. Subsequent actions tried Maven version overrides, repeated `mvn clean install` and `osv-scanner`, additional scanner syntax, and a destructive local-cache action `rm -rf ~/.m2/repository/org/springframework/boot/` at E242. This cache deletion is **observed**, not hypothetical; no evidence establishes it was necessary or safe in a shared Cloud Shell cache. E261 consulted scanner help late; E267 removed managed json-smart; E269 re-built. In E271 the agent **acknowledged scanner incompleteness** but still stated the task was complete and inferred mitigation from updated versions. Hook E272 allowed the stop **only because the denial bound was exhausted**, with deterministic acceptance explicitly still false.

**Decision on the user's three possibilities:**
- **Feedback not delivered or unclear? REJECTED for the main failures.** E29/E30, E74/E75, E189/E190 give explicit remaining findings, forbidden downgrade and 26 UNKNOWN after coverage regression, with baseline/progress comparison.
- **Feedback ignored? PARTIALLY SUPPORTED BEHAVIORALLY.** After receiving coverage failure E190, next action E191 downgraded Boot again instead of first restoring scanner comparability; final acknowledgment E271 did not prevent a completion claim. We cannot prove whether the model consciously disregarded feedback or failed to prioritize it across context.
- **Feedback misunderstood or inadequately integrated? STRONGLY SUPPORTED.** E73's “minor upgrade” rationale contradicts the no-downgrade constraint; E187 confused `results: []` from six filtered unscannable packages with successful remediation; E271 recognized uncertain scan but still declared complete. Subsequent alterations failed to protect the original dependency universe.
- **Guidance inadequate? POSSIBLE SECONDARY RISK, NOT PRIMARY EXPLANATION.** The relevant principles were present in the user contract and hook. The native context condensation events (five) have omitted payloads, so whether context compression reduced salience cannot be conclusively proven. The available Skill was not observably invoked through an explicit `SKILL.md` read in this 273-event trace (the `task_skill=0` flag only describes configuration); do not attribute causality to absence/presence of a Skill without stronger evidence.

**Efficiency/quality consequences:** 128 action events, including **47 non-view file edit actions**, **25 `mvn clean install` variants**, **15 OSV scanner commands**, four Stop Hook validations, and one Maven Boot-cache deletion. These are tool-action counts from exported trajectory, not necessarily all provider token/cost usage. This is greater unproductive activity than Task-15 (128 events total) and ended in no deterministically verifiable remediation.

**Highest-value bounded intervention:** improve the model-facing goal-preservation/reassessment contract, *not* the validator: after contrary evidence, a new engineering hypothesis must explain how it retains protected constraints and comparable observations of the original target graph; absence of scan findings with lost coverage must be treated as unavailable proof, never success. Before any major/minor/downgrade interpretation, verify semantic-version ordering rather than infer availability. Keep engineering choices model-owned and do not prescribe dependency recipes, release versions, a custom critic or a multi-agent workflow. Independently examine whether the native agent's condensation mechanism or prompt presentation de-emphasized task constraints; no proof of a specific context-loss bug yet. Separately assess authorization/safety for destructive shared Maven cache cleanup; do not silently introduce broad cache-resetting as a recovery technique.

**No extra live run required to establish the above facts.** A future focused test should establish whether the chosen single intervention prevents both premature completion and coverage-loss misclassification while retaining successful Task-15-like autonomous behavior.
