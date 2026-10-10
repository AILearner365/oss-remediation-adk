# Engineering evaluation scorecard — standard contract

Status: **ADOPTED for future OpenHands coding-agent evaluations** (2026-10-09). Scope: general autonomous software engineering; OSS/Maven remediation is a test case, not the definition of quality.

## How to score

Use the same nine dimensions for every evaluated run. Give each dimension **GOOD / MIXED / POOR / NOT EXERCISED / UNRESOLVED** and link to specific observable events, tool results, validator attempts, final diff and external facts where required. Record an evidence-confidence qualifier (**PROVEN / PARTIAL / NOT PROVEN / UNRESOLVED**) separately from the qualitative rating. A working tool, deterministic PASS or the model's own claim of success never establishes high engineering quality by itself. Do not infer hidden chain-of-thought or underlying training knowledge.

Rate each dimension against:
1. **Guidance effectiveness:** confirm exact guidance delivery; test observable adherence; do not infer causal benefit without controlled comparison.
2. **Evidence-driven reassessment:** contradictions recognized, assumptions revised, justified changes of direction and recovery.
3. **Technical correctness:** dependency compatibility and scope, test/runtime behavior, complete security evidence, justified exclusions and downstream impacts.
4. **Unsupported strategy selection:** consequential assumptions/versions/release claims verified *before* commitment; distinguish investigation from speculation.
5. **Strategy fixation:** repeated work on disproven premises versus purposeful error isolation; time to abandon false hypotheses.
6. **Preservation of progress:** identify healthier validated states; preserve or intentionally change them for evidenced reasons; assess regressions/recovery.
7. **Stale or inaccurate knowledge:** separate objectively wrong technical claims, outdated training information (often unprovable), invalid live assumptions, advisory drift, cache state and true infrastructure issues; check authoritative sources.
8. **Solution quality:** whether a defensible best choice among credible, relevant alternatives was considered when warranted; compatibility, minimality, maintainability, security, future upgrades, upstream/downstream effects. Do not demand gratuitous alternatives or claim global optimality.
9. **Performance and efficiency:** useful evidence/progress per consequential action, avoidable tool/edit/build/scan retries, duplicate work, elapsed time, token/cost, and necessary verification; compare only equivalent scopes and account for external drift.

For each future run: record task/branch/commit, model/SDK/tools, task-contract hash, guidance/critic configuration, initial advisory identities, number of completion attempts, final deterministic result, **engineering acceptance distinct from deterministic acceptance**, 9-row ratings with event links, first material divergence, a fact/assumption verification audit, meaningful alternatives, action and cost counts, confounders, and a narrowly justified next intervention. Preserve prior ratings; revisions require dated evidence.

## Historical ratings (October 2026)

Sources: [Task-05 analysis](GATE2-STOP-HOOK-TASK05-ANALYSIS.md) and [Task-06 analysis](GATE2-STOP-HOOK-TASK06-ANALYSIS.md). Ratings reflect reconstructed observable behavior. Task-05 used 25 baseline findings and default guidance; Task-06 had 26 findings (advisory drift) and the opt-in five-principle system-context suffix. No same-advisory paired causal trial exists.

| Dimension | Task-05 | Task-06 | Evidence-backed progression / remaining uncertainty |
| --- | --- | --- | --- |
| 1. Guidance effectiveness | **POOR** observed adherence to built-in reassessment guidance; added suffix **NOT EXERCISED** | **MIXED** observed adherence; suffix delivery **PROVEN**, causal effect **NOT PROVEN** | E27 Task-05/E53 Task-06 both chose forbidden Boot downgrade; Task-06 later recovered. Cannot attribute recovery to suffix. |
| 2. Evidence-driven reassessment | **POOR** | **GOOD** after hook feedback | Task-05 repeatedly reverted from valid Boot 4 states; Task-06 restored Boot 4 at E91 and used SBOM/version evidence to revise Jackson/Framework decisions. |
| 3. Technical correctness | **POOR** final build/scan/policies | **MIXED** overall; **GOOD within validator scope** | Task-05 finished broken with 25 UNKNOWN; Task-06 passed build/tests/scan and 26/26, but partial family overrides and limited tests leave production compatibility unproven. |
| 4. Unsupported strategy selection | **POOR** | **POOR** | Forbidden Boot 4→3 downgrade persisted as first consequential wrong choice; speculative BOM/version and false release claims recurred. |
| 5. Strategy fixation | **POOR** | **MIXED** | Task-05 repeated invalid parent/BOM/cache approaches; Task-06 had shorter Boot 3 episode, restored Boot 4 after second hook and did not relapse. |
| 6. Preservation of progress | **POOR** | **GOOD** after initial regression | Task-05 discarded intermediate passing Boot 4 builds; Task-06 preserved restored Boot 4 and successful direct fixes to acceptance. |
| 7. Stale or inaccurate knowledge | **POOR** externally incorrect artifact/family assumptions; stale *training cause* **UNRESOLVED** | **POOR** release/version verification; stale *training cause* **UNRESOLVED** | Task-05 nonexistent webmvc 3.2.5; Task-06 false Boot 4.0.6 characterization, nonexistent Spring 6.1.28, unverified patch-line alternatives. Advisory drift is proven, not model staleness. |
| 8. Solution quality | **POOR** incomplete solution | **MIXED**, **PASSES VALIDATION BUT HAS MATERIAL CONCERNS** | Task-06 individually overrides Tomcat/Micrometer/Jackson members without full release-family alignment proof; Boot 4.0.8 alternative was not evaluated. |
| 9. Performance and efficiency | **POOR** | **MIXED** | 407→255 events; 48→15 agent Maven installs; captured cost $1.2651→$0.9330. Task-06 still incurred invalid scans, speculative versions and editor churn; cannot isolate suffix's causal effect. |

**Run-level outcomes:** Task-05 **BOUNDED_FAIL**, Task-06 **DETERMINISTIC PASS (26/26)**, both **CONTINUE EVALUATION** as a platform decision. Neither demonstrates reliable best-choice selection; Task-06 is not yet production engineering acceptance. Do not average ratings into a universal harness score or treat one run as a statistical sample.

## Standard report template (copy for each new task)

- Run identity, commit, configuration, evidence directory and baseline identities:
- Deterministic completion / validator and scan coverage:
- Engineering acceptance / open risks:
- First material divergence (event + supporting evidence):
- Nine-dimension table: **dimension | qualitative rating | evidence confidence | event/report link | delta from comparable predecessor | demonstrated gap**.
- Tested credible alternatives, compatibility/downstream analysis, and untested possibilities:
- Action/observation, build/scan, failure, time/token/cost measures; avoidable versus justified work:
- Fact-versus-assumption audit; stale-model explanation only if supported:
- Cross-run confounders (model randomness, advisories, tooling/config drift):
- Smallest justified next experiment, or **no change**:
- Whether outcome qualifies for platform or delivery decision:

## Evaluation governance

This scorecard is an **evaluation/documentation contract**, not a new runtime policy, agent prompt, deterministic validator or nine hard-coded gates. Continue using one autonomous engineer with independent deterministic validation and native completion interception. Compare like with like. Every material future run should add one dated row/set of ratings and evidence references without erasing historical failures.
