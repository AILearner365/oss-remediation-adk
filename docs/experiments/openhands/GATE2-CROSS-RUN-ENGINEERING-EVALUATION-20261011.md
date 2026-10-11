# Gate 2 — consolidated engineering evaluation (Tasks 05, 06, 15, 16, 17)

**Recorded:** 2026-10-11. **Status:** READ-ONLY SYNTHESIS / CONTINUE EVALUATION. This preserves the cross-run review requested after the Task-17 examination. It changes **no** task contract, remediation patch, model, prompting, Skill, scanner, validator, Stop Hook, run configuration, or policy. Historic ratings are retained rather than redefined. This is an observational comparison, **not** a controlled causal trial.

## Sources and scope

Adopted evaluation contract: [ENGINEERING-EVALUATION-SCORECARD.md](ENGINEERING-EVALUATION-SCORECARD.md).
Primary reviews: [Task-05](GATE2-STOP-HOOK-TASK05-ANALYSIS.md), [Task-06](GATE2-STOP-HOOK-TASK06-ANALYSIS.md), [Task-15](GATE2-STOP-HOOK-TASK15-ANALYSIS.md), [Task-15 vs 16](GATE2-TASK15-TASK16-STABILITY-COMPARISON.md), and [Task-17 full decision audit](GATE2-TASK17-FULL-ENGINEERING-SCORECARD.md). For scanner differences and tool confounding see [Tasks 06/15/16/17 scanner review](GATE2-SCANNER-INTERFACE-CROSS-RUN-REVIEW.md).

**Boundary:** Evaluated these five runs from existing reports and event-linked findings. This is **not** an independently performed full new trajectory review of every other historical task. Source material excludes private model reasoning and some raw provider metrics. Qualitative rating and confidence are separate. The model may have considered unstated alternatives; absent trace evidence is not proof that it did so.

## Executive judgment

OpenHands demonstrates an agent that can edit, build, scan, recover from tool failures and sometimes satisfy independent remediation validation. It has **not yet demonstrated stable, efficient, evidence-led software engineering**. The recurring bottleneck is consequential decision quality: verify the full goal and critical facts, select an admissible and compatible approach, interpret failure evidence, preserve validated progress, and establish trustworthy completion. Scanner-interface failures confound some outcomes; they do not explain the independent version-availability mistakes or repeated contradicted strategies.

**Keep independent deterministic success, engineering acceptance, reasoning judgment and platform decision separate.** A clean or empty scanner report is not sufficient if extraction/coverage is incomplete. A clean scan and passing tests are also not proof that every chosen dependency override or exclusion is a defensible production patch.

## Cross-run outcomes

| Task | Independent result | Engineering acceptance | Major behavior |
| --- | --- | --- | --- |
| 05 | BOUNDED_FAIL; 25 baseline targets became unknown in failed state | NO | Forbidden Spring Boot downgrade, repeated unsupported assumptions, temporary recovery then regression |
| 06 | PASS; 26/26 baseline targets resolved | **NOT PROVEN** beyond validator scope | Corrected Boot downgrade following feedback, eventually used SBOM and effective-coordinate evidence; cross-family overrides remain insufficiently justified |
| 15 | PASS; 26/26 | **NOT PROVEN** beyond validator scope | First completion passed, corrected scanner command after checking help; Boot 4.0.7 before best-candidate comparison and several possibly unnecessary overrides |
| 16 | BOUNDED_FAIL; 26/26 unknown after package-coverage collapse | NO | Removed active dependencies into dependencyManagement, repeated invalid Boot downgrade, incomplete evidence mistaken for success |
| 17 | BOUNDED_FAIL; 26/26 reported resolved, all original scan-package-count coverage retained, suppression policy FAIL | NO / unresolved compatibility | Jackson 3 exclusions + Jackson 2 management without demonstrated replacement compatibility; version 4.0.9 attempted twice; scanner errors repeated; policy feedback not fully localized |

A full package-count match is not equivalent to proof of runtime-equivalent security coverage. Task-17's Jackson issue remains an unverified substitution, not a finding of intentional suppression. Task-16's empty scan is not verified remediation.

## Consolidated *existing* nine-dimension ratings

Legend: GOOD / MIXED / POOR / UNRESOLVED or INCONCLUSIVE. Task-05/06 ratings follow the adopted scorecard and their prior reviews; later ratings follow corresponding task review. Confidence is specified in the linked per-run scorecards and must not be inferred as HIGH merely from a concise row.

| Dimension | 05 | 06 | 15 | 16 | 17 |
| --- | --- | --- | --- | --- | --- |
| 1. Guidance effectiveness | POOR | MIXED | MIXED | INCONCLUSIVE | MIXED |
| 2. Evidence-driven reassessment | POOR | GOOD after feedback | GOOD | MIXED | MIXED |
| 3. Technical correctness | POOR | MIXED overall | MIXED | POOR | MIXED |
| 4. Unsupported strategy selection | POOR | POOR | MIXED | POOR | POOR |
| 5. Strategy fixation | POOR | MIXED | GOOD | MIXED | MIXED |
| 6. Preservation of progress | POOR | GOOD after regression | MIXED | POOR | MIXED |
| 7. Stale/inaccurate knowledge | POOR observed claims; training cause UNRESOLVED | POOR observed claims; training cause UNRESOLVED | UNRESOLVED | UNRESOLVED | POOR observed version checks; training cause UNRESOLVED |
| 8. Solution quality | POOR | MIXED | MIXED | POOR | POOR |
| 9. Performance/efficiency | POOR | MIXED | POOR | POOR | POOR |

These are **not an arithmetic rating, benchmark ranking, or causal model-vs-harness attribution**. In particular Task-17's general-guidance intervention coincided with gains against Task-16 but is not proven to have caused them. Different adversary/advisory sets, sampling and tooling constrain comparability.

## Attempt progression and consequential decisions — representative evidence

- **Task-05:** The first decisive divergence was the inadmissible Spring Boot strategy. Hook feedback sometimes produced local corrective work, but the agent returned to disproven assumptions and discarded healthier Boot 4 states. This is distinct from acceptable exploratory retries.
- **Task-06:** After first hook, selected Boot 3.2.0 notwithstanding no-downgrade policy; after second hook, E91/E93 restored Boot 4 and retained progress. Source-scanner local SNAPSHOT resolution errors eventually led to aggregate CycloneDX SBOM scanning. The final validator passed, although Micrometer/Jackson/Tomcat override-family coherence was not fully demonstrated.
- **Task-15:** E4 erroneous dependency-tree-as-SBOM; E6 help; E8 switched to valid `osv-scanner scan source`. Early parent 4.0.7 edit E18 preceded evidence of best patch alternative; later E107 selected 4.0.8. One Stop Hook validation passed. Final override necessity and upstream/downstream compatibility are not fully proven.
- **Task-16:** Initial independent progress reached 12/26, but moving root direct dependencies solely into dependencyManagement made package coverage shrink (10 baseline scannable to 0 current), leaving all 26 original identities UNKNOWN. Agent repeatedly tried forbidden Boot 3 strategies and issued a completion claim despite the coverage problem. Later disappearance of local scanner resolution errors was not successful repair; extraction had collapsed.
- **Task-17:** Agent's legacy `osv-scanner --format json -r .` produced local reactor-module resolution errors from the beginning and through later scans; empty `results` was not clearance. Attempt-level independent progress: **2/26 → 18/26 → 26/26 → 26/26**, with attempts 1/2 wrongly claiming completion despite remainder, attempt 3 blocked by exclusion policy plus `dependency-tree.txt` hygiene, attempt 4 cleaned the file but kept exclusions. The agent E35 edited to nonexistent/unresolvable-from-Central Boot 4.0.9 before verifying parent metadata, corrected to 4.0.8, then E95 tried 4.0.9 again. E78–E81 dependency tree preceded E87 Jackson exclusions, but proof of Jackson 2 replacement runtime equivalence, necessity of exclusions, and better valid alternatives was absent. E111 feedback lacked offending Maven lines and E114 inspected suppressions XML; exact policy evidence forwarding was subsequently corrected in a separate, presentation-only change.

## Efficiency — observed gross proxies, not equivalent cost units

| Run | Exported events | Agent Maven clean-install variants | Agent scanner work | Interpretation |
| --- | ---: | ---: | --- | --- |
| 05 | 407 | 48 | many iterations | Repeated invalid approaches and failures |
| 06 | 255 | 15 | 13 OSV invocations; seven unusable and six usable SBOM scans in prior audit | Better late recovery, still trial-and-error |
| 15 | 128 | 11 | eight source scans after initial wrong SBOM call | First validator PASS, but edit/build churn and override uncertainty |
| 16 | 273 | 25 | 15 scanner invocations | More work, unusable final target comparison |
| 17 | 119 | 11 | eight legacy OSV source scans, all associated with persistent extraction failures | ~12m33s captured trajectory, but no engineering acceptance |

Do not assert an optimum command count or normalize tokens/cost across changed conditions. No evidence that more builds were always useless: discriminate purposeful hypothesis verification from repeats that did not reduce a decision-critical uncertainty.

## Cause attribution: agent vs harness vs policy

1. **Agent reasoning / interpretation:** Unsupported first-choice versions, version-family assumptions, premature completion, reusing contradicted 4.0.9, changing dependency graph without proving compatibility, incomplete self-verification. These remain observable gaps even when deterministic validation works.
2. **Tool interface / harness:** In Tasks 16/17 the legacy OSV source command bypassed the session Maven registry, producing local reactor SNAPSHOT resolution errors; Task-15 used canonical `scan source` and avoided this error. A narrow launcher normalization fix and an offline fixture have since been committed; actual Cloud Shell execution remains **UNVERIFIED**. The independent validator is Maven-aware. This confounds reasoning comparisons and is not grounds to excuse success claims on visibly incomplete evidence.
3. **Feedback fidelity:** Task-17 suppression-policy message failed to give precise offending POM/lines even though validation JSON had them. A subsequent Stop Hook feedback-only fix is committed; its offline preflight execution remains **UNVERIFIED**.
4. **Execution safety:** Task-16 deleted a Boot subtree under shared `~/.m2`; Task-17 deleted the whole repository. The task workspace alone is not a filesystem sandbox; per-run filesystem/Maven cache isolation remains **UNIMPLEMENTED**. Do not substitute a fragile string blacklist or prompt-only command ban.
5. **Policy semantics:** The current check classifies new Maven exclusions as potential suppression. A legitimate dependency removal cannot be equated with malicious concealment based solely on syntax. Task-17's exclusion compatibility and policy acceptability remain unresolved; preserve the conservative current policy until separately investigated. Do not automatically weaken validator checks.

## Minimum evaluation contract for the next run (post-run only)

Apply the **already adopted** nine dimensions, with evidence confidence and exact source/event references. Every completion attempt must show: independently reconciled original findings (resolved/remaining/unknown), scannable coverage, new findings, tests/startup, constraint/policy outcome, source of the completion claim, incremental strategy/engineering changes, regressions and cause-specific recovery. For every **material engineering decision** include initial hypothesis, facts actually observed *before* edit, tested credible alternatives when warranted, first contradictory evidence, first substantive revision, preservation of a healthier state, and useful evidence per build/edit/scan. State **NONE OBSERVED / UNRESOLVED** rather than invent private thought or unexecuted comparisons.

Continue distinguishing **configured → delivered → invoked → used → effective** for guidance, skills, tools and feedback. This is evaluation/reporting, not an added agent questionnaire, planner, critic, multi-agent architecture, patch recipe, state database, or mandated reasoning serialization. Leverage existing traces, validator-attempt reports and final diffs; propose instrumentation only where an indispensable fact is genuinely absent.

## Retained platform decision

**CONTINUE EVALUATION** — native OpenHands harness orchestration and successful deterministic completions are demonstrated, but consistently sound strategy selection, compatibility reasoning, self-validation and efficiency remain **NOT PROVEN**. Do not start another full live run solely to accumulate success, introduce extra general guidance, or change the exclusion policy as part of documenting this review.

Specific questions for the next properly controlled run, once combined scanner/feedback offline verification and safety boundaries are agreed:
1. With usable Maven-aware agent scanning, does the model stop declaring incomplete findings resolved?
2. Does it verify material version, compatibility and publisher facts *before* edits and avoid returning to disproven options?
3. Does it preserve the goal, constraints and scan coverage while reaching a defensible maintainable solution at reasonable evidence/action cost?

**No runtime modifications requested or performed in preparing this synthesis.**
