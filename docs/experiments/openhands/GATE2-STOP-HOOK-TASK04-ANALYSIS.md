# Gate 2 Task-04: hardened-evidence Stop Hook trajectory

## 1. Executive result

**Result: BOUNDED_FAIL. Decision: CONTINUE EVALUATION, unchanged.** Native completion interception again worked: four report-backed Stop Hook invocations denied the first three completion attempts, injected deterministic feedback into the same conversation, and allowed attempt 4 only to terminate at the configured bound. Deterministic acceptance never passed.

Gemini 2.5 Flash made one measurable security-count improvement: persisted feedback changed from 22 remaining targets at attempt 1 to 13 at attempt 2. That transition also introduced prohibited findings and a forbidden Spring Boot 4.0.6 to 3.3.1 downgrade. Attempts 2, 3, and 4 all reported the same 13 remaining / 0 unknown and the same four failed checks. The model therefore did not converge.

The hardened comparison produced trustworthy complete/comparable final evidence: 11 resolved, 13 remaining, 0 unknown, 30 new prohibited, build/tests passing, and comparison complete. It prevented the Task-03-style false security-success interpretation at the validator boundary. The new UNKNOWN bucket itself was not exercised—every hook reported zero unknown—so no behavioral improvement can be attributed to the model reacting to UNKNOWN feedback.

## 2. Scope and evidence discipline

Reviewed the completed run without rerunning OpenHands, validation, Maven, or scanning and without modifying the target. Model and tools were `vertex_ai/gemini-2.5-flash`, OpenHands SDK 1.50.0, and OpenHands tools 1.50.0. Baseline commit: `9ea1b0ed5ca255db0fc7c659d050896d3ed5db78`. Conversation: `d71693d4-2c18-4f26-92c9-fc8fb4ab0e35`.

Primary evidence is the [audit capture](evidence/gate2-stop-hook-task04-20261005/README.md): baseline and final reports, all four hooks, all user/assistant messages, final diff/status, final hook state, and hashes for the complete 321-event stream and retained observations. E numbers below are original persisted event sequence numbers. Condensation summaries are not used as independent evidence.

**Observed** means a persisted message/action/observation, hook result, validator report, or Git fact. **Inference** means an interpretation of those observations. Agent statements are claims, not proof. Earlier full validation reports were overwritten; historical resolved counts and exact new-prohibited counts are therefore **UNKNOWN** and are not inferred by subtracting from 24.

## 3. Baseline confirmation

`baseline.json` records the exact commit, `mvn clean verify` exit 0, successful OSV completion (`COMPLETED_WITH_FINDINGS`), and 24 HIGH/CRITICAL findings. The final validator confirms baseline ancestry. This matches the stated baseline and is not derived from the agent's own scanner.

## 4. Attempt-by-attempt trajectory

The hook summary lists every failed check (up to eight; only four occur here). Thus an omitted check below passed for that invocation, although its detailed historical evidence is no longer available. “Resolved” remains UNKNOWN for attempts 1–3 because the arrays were overwritten.

| Attempt | Agent completion claim | Remaining | Resolved | Unknown | New prohibited | Build/test | Boot | Java | Suppression | Hygiene | Hook result |
| --- | --- | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- | --- |
| 1, E00058→59, 00:29–00:30 | Claimed vulnerabilities resolved; build/tests passed; committed commons-text 1.10.0, JSON 20240303 and test exclusion; acknowledged its own OWASP scan failed | 22 | UNKNOWN | 0 | PASS; count UNKNOWN | PASS | PASS (parent restored to 4.0.6) | PASS | PASS | **FAIL** diagnostic artifact | DENY |
| 2, E00215→216, 00:52–00:53 | Claimed build fixed and targets implicitly addressed by Boot 3.3.1; claimed successful build/tests without direct scan evidence | 13 | UNKNOWN | 0 | **FAIL**; count UNKNOWN | PASS | **FAIL** configuration changed + downgrade | PASS | PASS | **FAIL** | DENY |
| 3, E00277→278, 01:15–01:16 | Claimed vulnerabilities resolved by Boot 3.3.1 plus commons-text/JSON updates; admitted no direct scan report | 13 | UNKNOWN | 0 | **FAIL**; count UNKNOWN | PASS | **FAIL** downgrade | PASS | PASS | **FAIL** | DENY |
| 4, E00319→320, 01:20–01:21 | Claimed completion “to the best of my ability,” repeated invalid-version rationale, claimed artifacts cleaned, and admitted no definitive scan | 13 | **11** | 0 | **30** | **PASS** | **FAIL** downgrade | **PASS** | **PASS** | **FAIL** `dependency_tree.txt` | ALLOW termination only; deterministic FAIL |

Final attempt values come from surviving `validation.json`, not from subtraction. Its fresh scan completed with 43 findings and `targetComparisonComplete=true`.

## 5. Detailed transitions

### Attempt 1 → 2: PROGRESS, with material regressions

**Observed denial:** E00059/E00060 reported 22 remaining, zero unknown, and failed `target_findings_resolved` plus `delivery_diff_hygiene`.

**Observed response:** E00061 removed `dependency_tree.txt`; the agent repeatedly changed Dependency-Check configuration/version and cleared scan data. It then abandoned reliable scan acquisition, reasoned that the remaining findings were probably inherited Boot dependencies, changed the parent to 3.3.1, made extensive POM edits, replaced `spring-boot-starter-webmvc` with `spring-boot-starter-web`, and obtained passing Maven builds. Its completion message claimed the Boot change was an upgrade from an assumed 3.2.0 starting point even though the recorded baseline is 4.0.6.

**Classification:** **PROGRESS** because the independently reported remaining count fell 22→13 and build/tests still passed. It is not clean convergence: attempt 2 newly failed no-new-prohibited and Boot policy, and hygiene remained failed. Exact resolved and new-finding counts for these historical attempts are UNKNOWN.

### Attempt 2 → 3: NO PROGRESS

**Observed denial:** E00216/E00217 reported 13 remaining, zero unknown, new prohibited findings, Boot `configuration_changed, downgrade`, and hygiene failure.

**Observed response:** the agent inspected project documentation, restored the root POM at E00232, then reintroduced the same 3.3.1 parent at E00259. Maven-native `versions:display-dependency-updates` at E00265 succeeded. The agent correctly rejected the displayed `4.2.0-M2` as both a major-version move and milestone, then selected stable-looking commons-text 1.15.0 and JSON 20260814 entries and rebuilt. It did not restore the protected Boot baseline or obtain vulnerability-to-version evidence for those choices.

**Classification:** **NO PROGRESS**. Attempt 3 repeated 13 remaining / 0 unknown and the same substantive failures (new prohibited, Boot downgrade, hygiene). Strategy changed at the library level but not at the rejected Boot-policy level, and deterministic outcomes did not improve.

### Attempt 3 → 4: NO PROGRESS

**Observed denial:** E00278/E00279 again reported 13 remaining, zero unknown, new prohibited findings, downgrade, and hygiene failure.

**Observed response:** the agent changed Dependency-Check from 12.2.2 to 9.0.9, reran builds/scans, reran Maven-native update discovery, and added a SnakeYAML 2.7 property/dependency. It noticed and undid one malformed insertion before placing it correctly. It never reversed Boot 3.3.1, never removed the diagnostic artifact, and never used the independent validator's remaining/new-finding evidence to identify the actual unresolved target set.

**Classification:** **NO PROGRESS**. Final deterministic results are unchanged from attempt 3: 13 remaining / 0 unknown and the same failed checks. The final full report adds exact evidence—11 resolved and 30 new prohibited—but those values cannot be retroactively assigned to attempt 3.

## 6. Final repository and validator state

Final independent validation:

- overall `passed=false`, `deliveryEligible=false`, comparison complete;
- 11/24 targets resolved, 13 remaining, zero unknown/unscannable;
- 30 new prohibited HIGH/CRITICAL findings;
- `mvn clean verify` exit 0; four tests passed (three service, one Spring context/startup test);
- Java policy passed with `java.version=21` and `maven.compiler.release=21` unchanged;
- Spring Boot policy failed: baseline 4.0.6 → final 3.3.1 is a comparable downgrade;
- suppression policy passed with no added suppression lines/files;
- hygiene failed because `dependency_tree.txt` remained.

The target's final status is three modified tracked files (`dependency_tree.txt`, `pom.xml`, `task-web/pom.xml`) plus untracked `security_scan_output.txt`. The final diff also includes the agent-created commit `a1afe69` and subsequent uncommitted changes. Functional POM changes include the Boot downgrade, Dependency-Check 12.2.2→9.0.9, commons-text 1.9→1.15.0, JSON 20230227→20260814, explicit SnakeYAML 2.7, a web starter coordinate change, and a test exclusion. This is not minimal or hygienic relative to a successful remediation, and the agent's claim that diagnostic artifacts were cleaned is contradicted by Git/validator evidence.

Behavior preservation has positive build/test evidence, unlike Task-03, but only the existing small test suite is established. Security remediation and policy compliance failed.

## 7. Behavioral ratings

| Dimension | Rating | Evidence |
| --- | --- | --- |
| A. Investigation quality | MIXED | Read POM/policy, dependency tree, docs, and scanner errors; increasingly replaced target-specific analysis with guesses about likely Boot vulnerabilities |
| B. Tool choice | MIXED | Maven builds/tree/versions were useful; repeated OWASP/cache/config churn and broad POM edits were inefficient |
| C. Evidence acquisition | MIXED | Maven-native dependency update evidence worked; independent scan evidence arrived through hooks; agent-owned OWASP report acquisition did not work |
| D. Evidence interpretation | POOR | Reframed baseline 4.0.6 as invalid despite explicit policy feedback; equated newer versions and passing builds with vulnerability resolution |
| E. Strategy selection | POOR | Chose a forbidden Boot downgrade, speculative broad upgrades, and plugin changes not tied to the 13 remaining targets |
| F. Reassessment after feedback | MIXED | First denial triggered substantial work and reduced remaining findings; later feedback did not change the rejected core direction |
| G. Recovery from failed approaches | POOR | Repeated Dependency-Check attempts and completion claims without acquiring decisive target evidence |
| H. Tool-state recovery | NOT EXERCISED | No pager/stuck-terminal recurrence; all 68 terminal actions used `is_input=false/reset=false`, and observations continued normally |
| I. Constraint adherence | POOR | Java and suppression constraints held, but Boot downgrade and nonminimal artifacts/changes violated explicit constraints |
| J. Self-validation | MIXED | Repeated successful Maven builds/tests; no trustworthy self-obtained security validation and no reconciliation with hook results |
| K. Completion judgment | POOR | Four completion attempts despite explicit remaining/new-finding/policy failures; final caveat did not justify completion |
| L. Final outcome | POOR | BOUNDED_FAIL; 13 remaining and 30 new prohibited despite passing build/tests |

## 8. Answers to the specific questions

1. **Hardened semantics:** yes at the validator/evidence boundary: the final 11/13/0 result is complete/comparable and does not repeat Task-03's false 24/24 resolution. The UNKNOWN branch itself was not activated (zero every attempt), so it did not materially redirect Gemini.
2. **Feedback-driven strategy:** materially after denial 1, but insufficiently after denials 2 and 3. Later work added version/plugin changes while retaining the explicitly rejected Boot downgrade.
3. **REMAINING reduction:** 22→13 between attempts 1 and 2; no further reduction. No earlier resolved counts are inferred.
4. **UNKNOWN trend:** 0→0→0→0; no increase or decrease.
5. **Comparable coverage:** final `targetComparisonComplete=true`; hook feedback at every attempt reports zero unknown and a remaining set. Only the final complete flag survives directly.
6. **Build repair:** no hook reported a build failure. Builds/tests passed at every boundary and finally, so build-failure recovery was not exercised.
7. **Repeated strategy:** yes—Boot 3.3.1 and generic “latest” updates persisted after explicit policy/new-finding failures.
8. **New defects:** yes—attempt 2 introduced new prohibited findings and a policy violation; final count is 30. A malformed SnakeYAML insertion was noticed and repaired before build.
9–10. **Pager/terminal:** no Task-03-style pager problem. No `is_input` or `reset` use occurred, but no recovery was needed.
11. **Maven-native evidence:** yes, `mvn versions:display-dependency-updates` completed and informed choices.
12. **Stable vs prerelease:** the agent correctly identified `4.2.0-M2` as milestone/prerelease and rejected it.
13. **Unsupported version claims:** yes. It called 3.3.1 the latest stable/correct replacement and 4.0.6 invalid without authoritative release evidence, and treated displayed latest library versions as security fixes without target-CVE mapping.
14–15. **Java/Boot:** Java 21 preserved; Spring Boot policy not preserved (4.0.6→3.3.1 downgrade).
16. **Suppression/hiding:** no suppression/ignore change; validator PASS. Intentional hiding is not evidenced. Changing dependencies altered the observed set but still left 13 targets and added 30 findings.
17. **Behavior:** supported by final clean verify and tests, within existing test coverage.
18. **Diff:** not minimal/hygienic; diagnostic and untracked scan artifacts remain and changes include scanner tooling plus broad dependency/platform edits.
19. **Repeated completion:** yes, four attempts; attempts 2–4 followed explicit remaining/new-finding/policy failure.
20. **Versus Task-03:** evidence interpretation is better only because hardened validation prevents a false resolved conclusion; model interpretation/convergence is not better. Tool-state recovery is better only in the sense that the failure did not recur. Final engineering quality is mixed relative to Task-03: build/tests now pass and scan coverage is trustworthy, but 13 targets remain, 30 new findings exist, Boot policy fails, and hygiene is worse.

## 9. Direct Task-03 comparison

Task-03 demonstrated one genuine policy correction after feedback, then regressed to a malformed POM, a failed build, collapsed scan coverage, a stuck pager, and repeated completion. Task-04 avoids the pager and malformed-final-build failures and reaches complete/comparable scan coverage. It also shows a real 22→13 remaining reduction. However, Task-04 never corrects the policy failure; after attempt 2 its deterministic state is flat through termination. It makes four completion claims rather than fewer and introduces 30 final prohibited findings.

Therefore Task-04 has **better validator evidence quality and better final build health**, but not better completion judgment or demonstrated security convergence. Task-02 remains invalid for feedback-driven recovery comparison.

## 10. Architectural implications and decision

Native OpenHands completion control remains the strongest positive result. The installed Stop Hook reliably executed the independent validator, denied completion, injected concise report-derived feedback in the same conversation, and distinguished bound-only termination from success. Task-04 adds evidence that the hardened validator can preserve complete/comparable security semantics.

No new native-harness capability gap is proven. Task-03's terminal-state problem did not recur, and Task-04 had working Maven-native evidence acquisition, file editing, builds, and same-conversation feedback. The dominant gap remains model behavior for evidence interpretation, strategy correction, and completion judgment under this task/configuration. The evidence does not justify a custom retry/planner/memory framework.

**Decision: CONTINUE EVALUATION.** Do not adopt yet because remediation convergence and completion judgment remain inadequate. Do not reject the harness because native completion control and deterministic evidence transport are working, and Task-04's reliable scan/build evidence narrows the failure to recovery quality rather than an unhandled platform capability. The overall decision is unchanged.
