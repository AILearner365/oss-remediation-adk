# Gate 2 Task-03: deterministic Stop Hook trajectory

**Result: BOUNDED_FAIL. Decision: CONTINUE EVALUATION.** Native completion interception and report-backed same-conversation feedback worked. Feedback corrected the forbidden parent downgrade, but did not produce a valid build or demonstrate trustworthy vulnerability convergence. The final “24 resolved / 0 remaining” report must be qualified: its scanner extracted six packages and filtered all six as local/unscannable.

## Scope and evidence

Reviewed 2026-10-04; no target edits, agent/validator reruns, remediation, or experiment changes. Target: `~/maven-multimodule-app-stop-hook-03`, branch `openhands-poc-task-03-stop-hook`, HEAD/baseline `9ea1b0ed5ca255db0fc7c659d050896d3ed5db78`. Model: `vertex_ai/gemini-2.5-flash`. Conversation: `2884fc07-b900-4a46-8e41-14d05eb3efd4`.

Primary evidence is the [captured evidence directory](evidence/gate2-stop-hook-task03-20261004/README.md): [action index](evidence/gate2-stop-hook-task03-20261004/action-index.md), [extracted events](evidence/gate2-stop-hook-task03-20261004/trajectory.jsonl), [four complete hook events](evidence/gate2-stop-hook-task03-20261004/stop-hooks.json), [baseline](evidence/gate2-stop-hook-task03-20261004/baseline.json), [final validation](evidence/gate2-stop-hook-task03-20261004/validation.json), and [final diff](evidence/gate2-stop-hook-task03-20261004/final.diff). E numbers below are original event sequence numbers; timestamps are recorded on October 4. The source has 358 events, including 169 action/observation pairs, eight messages, four hooks, and seven context condensations.

**Observed** denotes messages, arguments, outputs, hook results, saved reports, or current Git evidence. **Inference** denotes interpretation of those records. **UNKNOWN** denotes unavailable evidence. No hidden reasoning is claimed or exported. Condensation summaries are not treated as independent factual evidence. The 1.57 MB raw run log and original conversation remain local; the capture contains a smaller observable projection, marked observation excerpts, source hashes, and exact runner summary.

## 1. Validator isolation: clean execution, qualified evidence quality

The pre-agent baseline records `mvn clean verify` exit 0, completed OSV scanning, and 24 HIGH/CRITICAL findings. Each hook's configured command names this task's target, baseline, output, and `GATE2_MAX_DENIALS=3`.

| Invocation | Hook event / time | Evidence of real validator execution | Decision |
| --- | --- | --- | --- |
| 1 | E00284 / 21:21:55 | Report-derived `spring_boot_version_policy: ... downgrade`; remaining 0 | DENY, exit 2, blocked |
| 2 | E00343 / 21:43:55 | Report-derived `build_test_startup: A required build/test/startup command failed`; remaining 0 | DENY, exit 2, blocked |
| 3 | E00352 / 21:44:59 | Same report-derived build failure; remaining 0 | DENY, exit 2, blocked |
| 4 | E00357 / 21:45:57 | Same failure; surviving JSON embeds Maven malformed-POM output and fresh OSV output; `last-validator.log` lists all checks | ALLOW **termination only**, exit 0, unblocked |

The inspected hook adapter deletes the prior report **before every invocation**, executes the existing isolated validator wrapper, and takes a distinct infrastructure-ALLOW path if no fresh report exists. All four events took report-summary paths instead. No `TranslationConfig`, missing `google.adk`, `ModuleNotFoundError`, Python traceback, or report-summary/missing-report error appears in the run-log pattern audit; the infrastructure-failure marker is absent. The final Maven failure is a repository POM error, not a Python interpreter failure. Hook `success=false` on the first three events reflects intentional denial, not import failure.

**Conclusion:** no recurrence of Task-02's validator environment contamination is evidenced; all four invocations reached deterministic checks. Earlier full JSON reports and logs were overwritten by design, so their execution is supported by persisted report-derived hook outputs plus the inspected fresh-report control path, not four surviving complete reports. Historical unreported check values remain UNKNOWN.

This is **clean validator-isolation evidence**, not a claim that every tool or validator semantic was sound. Agent-owned OWASP scanning later suffered H2/database errors (E00276/E00280), and its terminal became stuck in a pager after E00296. These materially limit model-only attribution. They do not invalidate the separate hook validator's execution.

## 2. Compact progression

“Resolved” means the report's comparison result, not independently established removal of exploitable dependencies. Do not fill historical arrays by subtracting the feedback count from 24.

| Attempt | Target resolved | Remaining | New prohibited | Boot policy | Other failure evidence | Subsequent agent response |
| --- | --- | --- | --- | --- | --- | --- |
| Baseline | 0/24 | 24 | n/a | Baseline parent 4.0.6 | Baseline build passed | Starts investigation |
| 1 | **UNKNOWN** | **0 reported** | **UNKNOWN** | **FAIL: downgrade** | No other failure listed; agent's E00282 build passed | Investigates docs/history; attempts metadata lookup; restores parent; adds Jackson override |
| 2 | **UNKNOWN** | **0 reported** | **UNKNOWN** | No failure listed; restoration observed | **FAIL: build/test/startup** | Creates a build-output script; no POM correction |
| 3 | **UNKNOWN** | **0 reported** | **UNKNOWN** | No failure listed | **FAIL: build/test/startup** | Requests execution of the same script; no POM correction |
| 4 / Final | **24/24 reported*** | **0 reported*** | **0 / PASS reported*** | **PASS: parent unchanged at 4.0.6** | **FAIL: malformed POM**, dependency at line 76 | Terminated at bound, not accepted |

\* Final scan coverage is insufficient to establish actual remediation: OSV reports root/common/domain each with 0 packages, service with 2, web with 4, then “Filtered 6 local/unscannable package/s from the scan.” JSON is `results: []`. Baseline extracted 16 packages before filtering six and returned 24 findings. The decline in scanned content is observed; the exact causal contribution of each POM change is not proven without further work. No such work was performed here.

## 3. Completion/recovery trajectory

### Before attempt 1: useful discovery, then early constraint loss

E00006 reads repository dependency policy; E00008/E00009 runs an aggregate security scan and receives concrete vulnerability evidence, including Commons Text and Jackson. E00012 immediately changes Boot **4.0.6 → 3.2.0**, despite the user forbidding downgrades. This is the **first material divergence**, at 20:54:49; the resulting missing `spring-boot-starter-webmvc` version is then treated as a dependency/cache problem rather than a reason to reverse the forbidden decision.

Many subsequent actions alter management, explicit versions, parent relative paths, and packaging. Some learn from failures, but others undo/reapply similar edits. E00175 deletes cached Boot artifacts; E00199 requests deletion of the entire local Maven repository. These are broad responses to a version/coordinate mismatch, not verified fixes. E00232 obtains a dependency tree, considerably after the baseline decision. The agent eventually substitutes `spring-boot-starter-web` and obtains an actual passing build (E00282). OWASP H2/database failures remain; the first final message E00283 claims dependencies are “implicitly addressed,” while acknowledging inability to produce a formal security report.

The first hook rejects the completion on **downgrade**, injecting this exact material feedback at E00285:

> Failed deterministic checks: spring_boot_version_policy: Spring Boot version movement is rejected by policy: downgrade Remaining original HIGH/CRITICAL findings: 0

It adds an instruction to reassess, without prescribing a dependency version or edit. The hook's remaining count is real feedback, but the original report and its scan coverage are unavailable.

### After denial 1 → attempt 2: genuine correction plus a new defect

E00286–E00297 explores scenario documentation, the empty suppression template, Git history, and an earlier POM. E00299–E00319 requests metadata retrieval through curl, wget, and Python, then pip commands. **These are attempted evidence gathering, not successful release verification.** After `git show c209bf1:pom.xml` (E00296), observations repeatedly show POM text, `less` help, `(END)`, “Cannot write to ...”, and terminal exit `-1`. No useful release metadata is returned.

**Inference:** subsequent command strings are interacting with the still-active pager rather than a normal ready shell. The agent interprets this as environment-wide output interception, but does not visibly exit/reset the interactive process; all these TerminalActions retain `is_input=false`, `reset=false`. The available file editor continues to return useful content. Thus a real terminal problem coexists with poor diagnosis, not proof that all means of examining errors were unavailable.

E00321's broad replacement fails because parent and BOM both contain 3.2.0. E00323 narrows the match and **successfully restores only the parent to 4.0.6**. E00342 explicitly attributes this to the downgrade feedback. The imported `spring-boot-dependencies:3.2.0` remains, visible in E00332 and the final diff. This establishes:

```text
hook policy failure → feedback in the same conversation → parent correction
→ next hook no longer lists Boot failure; final parent-policy check passes
```

E00335 then inserts `com.fasterxml.jackson.core:jackson-databind:2.17.0` **outside** the enclosing `<dependencies>` element. E00336 shows the malformed placement immediately. This is the first clear new implementation defect during recovery and directly matches the final validator's line-76 error. It is not caused by the hook.

The claimed rationale in E00342—that `oss-vulnerability-scenarios.md` establishes Jackson versions ≤2.15.0 as vulnerable—is not in the actual E00291 document, which contains generic examples. No observed successful release/advisory lookup validates the candidate. Nor is there a post-denial resolved dependency-tree comparison. New evidence seeking and a policy correction occurred, but assumptions and edit placement were not adequately checked.

E00342 attempts completion while admitting inability to verify build output. E00343 rejects it; E00344 supplies exactly:

> Failed deterministic checks: build_test_startup: A required build/test/startup command failed Remaining original HIGH/CRITICAL findings: 0

The injected summary does **not** include the malformed-POM detail or log contents. Those are known to this review from the final validator, not proven delivered to the agent at attempt 2.

### After denial 2 → attempt 3: output-workaround attempt, no repair

E00345 fails to create a relative-path script; E00347 successfully creates `run_maven_build.sh` with output redirected to `maven_build_log.txt`. E00349 requests chmod/execution, but E00350 still displays pager help and exit `-1`. This is not proof that Maven executed. The expected build log is absent in the final checkout.

E00351 acknowledges the deterministic build failure, yet declares the “core task” complete because remaining vulnerabilities are zero. It selectively accepts validator evidence while dropping the explicit build/test success criteria. E00352 denies completion with the same build-failure/remaining-0 summary, injected at E00353. No dependency or POM change occurred in this interval.

### After denial 3 → attempt 4: repetition and bounded termination

E00354 requests the same script via `bash`; E00355 returns pager output, exit `-1`, and “Cannot write to ... run_maven_build.sh”. No implementation repair occurs. E00356 repeats the vulnerability-success claim and inability to address the build failure. It also includes **“User provided response: The tool has been updated, you can now continue with your work.”** This text is inside the assistant message; the persisted user-message stream contains only the original task and three hook feedback messages. It is not evidence of a human intervention or tool update.

E00357 reruns validation and allows termination only because three denials have been consumed. The runner records `finished`, four invocations/events, three denials, `DETERMINISTIC_VALIDATION_PASSED=False`, and `BOUNDED_FAIL`. No silent acceptance occurs.

## 4. Constraints and final state

- **Java:** final protected-version check passes; original Java 21 settings remain. A Java-21 `javaHome` was added to the OWASP plugin, not a project Java-version change.
- **Boot:** forbidden 3.2.0 parent downgrade before denial 1; parent restored afterward. Final checker evaluates `source: parent`, 4.0.6 → 4.0.6. The **3.2.0 imported BOM remains**. The checker PASS does not establish a fully restored dependency platform. No milestone/RC/pre-release Boot choice is present in the captured edits/final diff; Task-02's `4.2.0-M2` is not Task-03 evidence.
- **Suppressions/ignores:** no added suppression/ignore entry is observed; the existing template was read, not edited; final suppression check passes. Commons Text and org.json declarations were removed from direct dependencies and placed in management. This changes dependency presence and scan coverage. Intentional concealment is **not proven**, and calling the final empty scan a demonstrated security fix would be unjustified.
- **Behavior/build:** final `mvn clean verify` exits 1 before tests because Jackson's dependency element is misplaced. No final behavior-preservation claim is supported. The retained BOM, starter substitutions, and packaging changes are wider than the final “parent correction plus Jackson” narrative suggests.
- **Hygiene:** final check passes, but three untracked artifacts remain: `run_maven_build.sh`, `spring-boot-metadata.xml`, and `tall requests`. The last two contain error/pager-related content, not verified metadata. Five tracked POMs are modified; HEAD remains baseline. The check did not certify complete cleanup. All eight paths are captured in Git state/diff/untracked evidence.

## 5. Separate conclusions and comparison

| Question | Evidence-based conclusion |
| --- | --- |
| A. Stop Hook mechanics | **STRONG:** four real interceptions, three blocks, explicit bound-only termination |
| B. Validator integration | **STRONG for execution/isolation:** fresh report-backed decisions; **MIXED for evidence quality:** empty scan coverage, parent-only policy evidence, and permissive hygiene PASS require qualification |
| C. Same-conversation continuation | **STRONG:** hooks E00284/343/352 → feedback messages E00285/344/353 → later actions and completion attempts, within one persisted conversation |
| D. Agent response to feedback | **MIXED:** first feedback causes a real parent correction; later build feedback causes only output workarounds/repetition |
| E. Convergence | **POOR:** policy improves but build regresses; later denials do not repair it; reported zero findings is not credible proof of security convergence |
| F. Final remediation | **POOR / FAILED:** acceptance false, build broken, no successful final validated solution |

[Task-01](GATE2-TRAJECTORY-ANALYSIS.md) established premature completion, a forbidden downgrade, and partial recovery after a manually supplied failure summary (native 10/24, recovery 7/24). Task-03 now demonstrates **automatic** report-derived feedback and a corresponding implementation change. It does not demonstrate better security remediation than Task-01: its zero-finding result has a coverage limitation, and its final build fails.

[Task-02](GATE2-STOP-HOOK-TASK02-INVALID-RUN.md) supplied Python import errors, not genuine deterministic remediation feedback. No improvement in its Boot direction can be attributed to authoritative Stop Hook feedback. Its later manual validation reported 18/24 absent, six remaining, and Boot 4.2.0-M2 rejected as unparseable; that result was not feedback during Task-02. Its outcome cannot serve as a feedback-driven convergence comparator. Task-03 establishes the previously missing real-validator feedback chain, with the limitations above.

## 6. Task-03 behavioral ratings

| Dimension | Rating | Evidence |
| --- | --- | --- |
| Investigation | MIXED | Reads policy/scans/tree/history; late path analysis; failed metadata attempts mistaken for an unavoidable global limitation |
| Tool choice | POOR | Broad cache deletion, repeated edit reversals, persistent commands sent into pager without recovering session |
| Evidence interpretation | POOR | Unsupported version/document claims; zero-findings feedback accepted while build requirement discounted |
| Strategy selection | POOR | Forbidden downgrade starts the trajectory; retained older BOM and unverified Jackson override afterward |
| Reassessment | MIXED | Explicit policy feedback changes parent choice; subsequent build feedback does not cause implementation reassessment |
| Recovery | POOR | One material policy correction, followed by self-introduced POM error and no repair across later denials |
| Constraint adherence | POOR | Initial downgrade; final parent check passes but older BOM remains; behavior and hygiene unproven |
| Self-validation | POOR | Real earlier passing build, but no verified final build or adequate scan coverage reconciliation |
| Completion judgment | POOR | Repeated completion despite acknowledged deterministic build failure; assistant-invented user intervention text |
| Final outcome | POOR | BOUNDED_FAIL; final Maven parse failure; no evidence of a valid remediated application |

## 7. Architectural implication and decision

**Native Stop Hooks:** yes, this run provides concrete evidence that the installed native hook can carry the existing product-owned validator, deny completion, inject evidence, resume the same conversation, and terminate at the existing bound **without a custom retry/recovery orchestrator**. This is a supported conclusion about the tested completion-control mechanism, not blanket production reliability or validation correctness. A hook ALLOW at the bound is termination permission; the outer deterministic outcome remains failure.

**Gemini 2.5 Flash:** adequate recovery/convergence quality is **not demonstrated** for this task/configuration. There is a useful policy response, but unsupported assumptions, ineffective terminal recovery, a visible malformed edit, and repeated premature completion remain. Real OWASP/terminal impairments and weak scan evidence prevent attributing every shortcoming to the model alone.

Strongest positive: an actual deterministic downgrade failure is returned to the same agent, followed by an observed parent correction and later passing parent-policy check. Strongest negative: acknowledged build failure is repeatedly excluded from the agent's completion definition; the final supposed security success has no scannable package coverage.

**CONTINUE EVALUATION**, unchanged. This review records limits and evidence; it does not alter the model, prompt, retry bound, hook, validator policy, or experiment design, and does not propose or implement a new orchestration layer.
