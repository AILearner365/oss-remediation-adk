# Gate 2 Task-15 vs Task-16: stability and engineering-reasoning assessment

Status: **CONSOLIDATED EVIDENCE-BACKED COMPARISON; EVENT-LEVEL ATTRIBUTION INCOMPLETE**. 2026-10-11. Review only; no agent, guidance, Skill, runtime or validator changes made.

## Verdict

**Task-16 was an actual controlled-configuration replication that failed, not an ADC failure.** The earlier Task-16 startup failure (`20261011T031548Z`, `stage=STARTUP`) is a separate record, with `structured_guidance=0`. The later actual trial (`20261011T033535Z`, Task-16) has the intended `engineering_judgment_guidance=0`, `task_skill=0`, `structured_guidance=1`; model `vertex_ai/gemini-2.5-flash`; `max_denials=3`; `max_iterations=250`. Recorded hashes of guidance/context/Skills match Task-15. Target baseline Git SHA `9ea1b0ed5ca255db0fc7c659d050896d3ed5db78` matches Task-15. Control head differs because the evaluation review and failed-startup evidence were subsequently committed; review these for any change to agent-consumed content, rather than treating the mere control SHA change as an effective configuration change.

**Task-15 deterministic PASS; Task-16 deterministic BOUNDED_FAIL.** Replication therefore does **not** establish stable autonomous remediation. Strongest recurring problem is unsupported strategy/constraint management; newly decisive Task-16 failure is loss of scan coverage after editing dependency declarations. The validator correctly blocked false success.

## Evidence pointers and limitations

- [Task-15 baseline assessment](GATE2-STOP-HOOK-TASK15-ANALYSIS.md) and [Task-15 run](evidence/gate2-orchestrated-run-20261011T010954Z/README.md).
- [Task-16 run](evidence/gate2-orchestrated-run-20261011T033535Z/README.md); [metadata](evidence/gate2-orchestrated-run-20261011T033535Z/run-metadata.txt); [final diff](evidence/gate2-orchestrated-run-20261011T033535Z/final.diff); [Git state](evidence/gate2-orchestrated-run-20261011T033535Z/git-state.txt); [validation 1](evidence/gate2-orchestrated-run-20261011T033535Z/validation-attempt-1.json), [validation 2](evidence/gate2-orchestrated-run-20261011T033535Z/validation-attempt-2.json), [validation 3](evidence/gate2-orchestrated-run-20261011T033535Z/validation-attempt-3.json), [validation 4](evidence/gate2-orchestrated-run-20261011T033535Z/validation-attempt-4.json); [event trajectory](evidence/gate2-orchestrated-run-20261011T033535Z/trajectory-0955955ec6de48c1a53bb4e46e9d1ee1/events.jsonl).
- **Material evidence-access limit:** the published 2,234,011-byte Task-16 JSONL trajectory could not be returned through the available file reader (empty content due size); GitHub raw fetch also failed its size restriction. Its manifest reports 273 events, but this review **has not independently parsed the 273 event bodies**. Conclusions below are from the four detailed independent validator checkpoints, the final patch and run metadata; they are **not** a complete action-by-action timeline and cannot establish which instruction the agent read, when the agent invoked a Skill, exact command/edit counts, causal model intent, or first failure localization. Do not present them as if full event-level review occurred. The next instrumentation/analysis step, if required, is to analyze the JSONL locally in Cloud Shell and publish a compact action timeline or smaller trace shards; this is a read-only analysis, not a reason to launch another live run.

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
