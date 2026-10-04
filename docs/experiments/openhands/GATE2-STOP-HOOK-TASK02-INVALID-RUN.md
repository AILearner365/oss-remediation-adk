# Task-02 — invalid Stop Hook recovery experiment

## Purpose and classification

Evidence review only, recorded 2026-10-04. **Task-02 classification: INVALID FOR RECOVERY/CONVERGENCE COMPARISON because validator execution was infrastructure-confounded.** Native hook mechanics and partial remediation remain useful observations. Overall OpenHands decision: **CONTINUE EVALUATION**.

No agent or validator was rerun for this review. The target repository, validator, Stop Hook, retry bound, prompt, and experiment design were not changed.

## Baseline

The preserved [baseline.json](evidence/gate2-stop-hook-20261004/baseline.json) records:

- Commit `9ea1b0ed5ca255db0fc7c659d050896d3ed5db78`, base branch `main-runrunning`.
- Worktree `~/maven-multimodule-app-stop-hook`, task branch `openhands-poc-task-02-stop-hook`; current HEAD and branch still match ([workspace review](evidence/gate2-stop-hook-20261004/workspace-review.json)).
- Maven `mvn clean verify`: exit 0 / BUILD SUCCESS.
- OSV scan: `COMPLETED_WITH_FINDINGS`, 24 original HIGH/CRITICAL findings.
- Protected Java 21; Spring Boot parent 4.0.6; no baseline suppression files.

The baseline's `experiment` field misleadingly says `openhands-gate2-task-01`; its targetRepository, taskBranch, and commit identify Task-02. Preserve this original metadata defect rather than rewriting evidence. The manual report also passes baseline ancestry. These facts support baseline identity and successful baseline capture; they do not reconstruct an otherwise unrecorded initial Git status.

## Observed run result and native mechanics

The already committed [run.log](evidence/gate2-stop-hook-20261004/run.log) ends with:

```text
MODEL=vertex_ai/gemini-2.5-flash
CONVERSATION_ID=d5e63cec-64d2-4527-acd0-eb62d3161982
FINAL_STATUS=finished
STOP_HOOK_INVOCATIONS=4
STOP_HOOK_EVENTS=4
DENIED_COMPLETIONS=3
DETERMINISTIC_VALIDATION_PASSED=False
GATE2_STOP_HOOK_RESULT=BOUNDED_FAIL
```

[attempt-count](evidence/gate2-stop-hook-20261004/attempt-count) is 4. The concise [persisted event index](evidence/gate2-stop-hook-20261004/stop-hook-event-index.json) preserves event IDs, parent links, timestamps, source hashes, and hook feedback from the one conversation:

| Stop event sequence | Timestamp as persisted (2026-10-04) | Result | Continuation evidence |
| --- | --- | --- | --- |
| 147 | 20:03:26.491490 | DENY, blocked, exit 2 | feedback 148 → agent message 149 |
| 150 | 20:03:36.908570 | DENY, blocked, exit 2 | feedback 151 → agent message 152 |
| 153 | 20:03:48.720390 | DENY, blocked, exit 2 | feedback 154 → agent action 155; later message 159 |
| 160 | 20:04:10.459281 | ALLOW, exit 0, bound reached | run reports finished, not accepted |

Each hook has `hook_input.reason=agent_finished` and an agent-message parent. This proves completion interception, emitted Stop events, same-conversation continuation, and bounded termination in Task-02 itself. It does not require relying solely on the earlier dummy POC.

## Infrastructure confounder

The first concrete failure is Stop event 147, attempt 1, whose feedback includes:

```text
AttributeError: module 'google.genai.types' has no attribute 'TranslationConfig'
```

The same error appears in attempts 2 and 3 and the fourth bounded-termination reason. The preserved [last-validator.log](evidence/gate2-stop-hook-20261004/last-validator.log) contains the full final traceback: validator import → control-repository agent imports → host `/usr/local/lib/python3.12/dist-packages/google/adk` → Pydantic under `/tmp/openhands-uv-cache/archive-v0/KWHR3vxZBV_q__Lh/lib/python3.12/site-packages` → missing `TranslationConfig`.

The child validator inherited/conflicted with the active OpenHands uv package environment, mixing host ADK and ephemeral packages. It failed during import before executing deterministic checks. No `validation.json` survives, and contemporaneous documentation in commits `f6cd8760` and `90cb79de` records that none was produced. Every denied event carries the traceback fallback, not report-derived Maven/OSV/policy checks. The historical adapter at `a1e303a7:scripts/openhands/openhands-gate2-stop-hook.sh` falls back to the log tail when there is no report summary, labels it `DETERMINISTIC_VALIDATION_FAILED`, and consumes a denial attempt. That behavior explains the misleading run classification.

Only the last full validator log survives; earlier failures are evidenced by persisted hook feedback. There are no per-attempt deterministic reports to reconstruct.

## Why the denials are invalid for recovery analysis

The hook mechanism worked, but its three denials were infrastructure errors mislabeled as deterministic remediation failures. They contained no trustworthy unresolved-finding or policy assessment. Neither the `DETERMINISTIC_VALIDATION_FAILED` label nor `BOUNDED_FAIL` establishes that real validation ran. These are not three successful rounds of deterministic remediation feedback.

The later manual report cannot retroactively supply feedback to the agent. No attempt-by-attempt reasoning assessment or causal claim about remediation progress follows from these denials.

## Manual post-run deterministic validation

The existing `~/.openhands/gate2/task-02-stop-hook/manual-validation.json` is summarized without rerunning it in [manual-validation-summary.json](evidence/gate2-stop-hook-20261004/manual-validation-summary.json), including its SHA-256, checks, finding identities, and tree digest. The supplied handoff identifies this as the manual run outside the contaminated uv environment; the JSON itself does not record interpreter/environment provenance. Its Maven output records the run around 20:24, after the agent finished around 20:04.

| Check | Result |
| --- | --- |
| baseline_ancestry | PASS |
| git_change_evidence | PASS |
| build_test_startup | PASS (`mvn clean verify`, exit 0) |
| fresh_vulnerability_scan | PASS / COMPLETED_WITH_FINDINGS |
| target_findings_improved | PASS: 18 of 24 original findings absent |
| target_findings_resolved | FAIL: 6 original HIGH/CRITICAL findings remain |
| no_new_prohibited_findings | PASS |
| protected_java_version | PASS |
| spring_boot_version_policy | FAIL: `unparseable`, 4.0.6 → 4.2.0-M2 |
| suppression_policy | PASS |
| delivery_diff_hygiene | PASS |
| Overall / delivery eligible | FAILED / false |

This is **partial remediation capability**, not no progress and not final success. “18 resolved” means absent from the recorded fresh scan against the baseline identities.

The report and current Git status list only `pom.xml`, `task-service/pom.xml`, and `task-web/pom.xml`. The read-only [current workspace diff](evidence/gate2-stop-hook-20261004/final-workspace.diff) is 58 insertions and 2 deletions. It directly supports Boot 4.2.0-M2, jackson-databind 3.1.4, root commons-text **1.10.0**, web log4j-api/log4j-to-slf4j 2.26.1, and service test-scoped Log4j 2.23.1. The agent's commons-text **1.11.0** completion claim is not supported by that POM. Do not generalize jackson-databind's version to every Jackson component or treat model completion claims as scanner evidence.

The manual report's temporary diff is no longer available. The current diff is explicitly a review-time snapshot, not a claimed byte-identical historical diff. The report's recorded tree digest is retained in the summary.

Spring Boot qualifier handling intentionally fails closed (see the [existing policy test](../../../tests/unit/test_autonomous_spring_boot_policy.py), including 4.0.0-RC1). The observed 4.2.0-M2 is not automatically an acceptable minor upgrade. Validator policy is unchanged.

## What Task-02 proves

| Question | Conclusion |
| --- | --- |
| A. Native OpenHands Stop Hook invocation | PROVEN |
| B. Same-conversation continuation | PROVEN by persisted event parent chains |
| C. Real validator integration | FAILED / INFRASTRUCTURE-CONFOUNDED |
| D. Agent remediation capability | PARTIAL, from later manual validation |
| E. Deterministic feedback-driven recovery | NOT VALIDLY TESTED |
| F. Final remediation success | FAILED |

## What Task-02 does not prove

Task-02 cannot validly answer whether deterministic failure evidence improved reasoning, whether feedback caused strategy reassessment, whether same-conversation validator feedback improved convergence, or whether multiple Stop Hook denials drove remediation progress. The denials were caused by validator infrastructure failure. Do not attribute improved dependency choices to the Stop Hook.

[Task-01](GATE2-TRAJECTORY-ANALYSIS.md) had no deterministic completion interception: the agent could finish despite subsequent independent validator disagreement (including after externally supplied recovery feedback). Task-02 added interception, but the child validator was broken, so it still did not establish a valid deterministic remediation feedback loop. Task-03 is the first clean Stop Hook plus real deterministic validator recovery experiment; its separate evaluation must not treat Task-02 as a valid recovery/convergence comparator. Existing local Task-03 evidence records report-derived denials and no import traceback; that untracked evidence is outside this commit's scope.

## Isolation fix introduced afterward

Implementation history: `88ad8c86` isolated the validator; `68ee33d6` and `ded875a5` separated infrastructure failure handling/reporting; `1acddfd4` added host interpreter dependency probing. Documentation followed in `1ff64381` and `642ce933`.

- [Validator wrapper](../../../scripts/openhands/openhands-gate2-validate.sh) selects host Python outside active `VIRTUAL_ENV`, probes `google.adk` and `pydantic`, removes `VIRTUAL_ENV`, `PYTHONHOME`, and inherited `PYTHONPATH`, and sets `PYTHONPATH` to the control repo.
- [Stop Hook](../../../scripts/openhands/openhands-gate2-stop-hook.sh) removes stale output; missing fresh validation output creates an infrastructure-failure marker and permits termination rather than consuming deterministic denial attempts.
- [Runner](../../../scripts/openhands/openhands-gate2-stop-hook-run.py) reports `INFRASTRUCTURE_FAIL` distinctly.

The later local `uv-validation.json` has the same recorded tree digest and 18/6 outcome as the manual report, consistent with the subsequent isolation check; it is not evidence that validation worked during Task-02. Neither implementation nor policy was modified for this review.

## Evidence retention

Original run.log, last-validator.log, baseline.json, and attempt-count were already committed in `a1e303a7` and match the local source bytes. They are referenced, not duplicated. Added only concise manual-result/event/state extracts and the small POM diff; full conversation persistence and base_state.json remain local. Source hashes permit audit against the preserved local reports/events.

**Final classification: INVALID FOR RECOVERY/CONVERGENCE COMPARISON. Overall decision: CONTINUE EVALUATION.**
