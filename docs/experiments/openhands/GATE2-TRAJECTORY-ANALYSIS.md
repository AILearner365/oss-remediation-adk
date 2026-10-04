# Gate 2 OpenHands trajectory analysis

Decision: **CONTINUE EVALUATION — not ADOPT, not REJECT.** Recorded 2026-10-04.

Both phases failed the remediation acceptance criteria. The trajectory nevertheless demonstrates working investigation/edit/build/scan capabilities and a material response to external failure evidence. It also demonstrates constraint loss, repeated unproductive actions, unsupported dismissal of findings, and unjustified completion twice. A passing build did not establish security success.

## Scope and evidence standard

This evaluates the observed OpenHands harness/model/tool combination, not just its final diff. No remediation edits, agent reruns, validator reruns, or harness redesign were performed for this analysis. The control branch is `openhands-poc-evaluation`; the target is `AILearner365/maven-multimodule-app`, branch `openhands-poc-task-01`, baseline `9ea1b0ed5ca255db0fc7c659d050896d3ed5db78` (`main-runrunning`). Existing [setup](OPENHANDS-VERTEX-POC.md), [experiment protocol](GATE2-NATIVE-REMEDIATION.md), [task](GATE2-TASK.md), preparation/baseline/validation scripts, and handoff were inspected first.

**Observed** means persisted user/assistant messages, action summaries, tool arguments, observations, or saved deterministic results. **Inference** means an assessment of that evidence, not access to private reasoning. **Unknown** means not established by the captured record. Internal reasoning/thought fields and opaque provider signatures are excluded from the export and are not the basis of the judgments below. Reasons inferred from tool choice are explicitly identified as such.

### Evidence inventory and provenance

- [Conversation index](evidence/gate2-20261004/conversation-index.md): full user and final assistant messages, action summaries, edit/command arguments, and observation references.
- [Observable events JSONL](evidence/gate2-20261004/events.jsonl): 366 records, E00000–E00365, exported directly from `~/.openhands/agent-canvas/dev_conversations/c06a12ed24424277a8200f309ca6cdc8/events/event-*.json`. Each JSONL line is original sequence + 1. Includes 115 actions paired with 115 observations, six messages, one system-prompt event, and 129 state-update records (stats payloads omitted).
- [Manifest](evidence/gate2-20261004/manifest.json): exact source filenames, SHA-256 hashes of original bytes, export hashes, and omissions. [Capture notes](evidence/gate2-20261004/README.md) describe reproduction and limits.
- [Baseline](evidence/gate2-20261004/baseline.json) and [recovery validator](evidence/gate2-20261004/validation.json): sanitized snapshots of `~/.openhands/gate2/task-01/{baseline,validation}.json`. They contain OSV findings, checks, and embedded build evidence. Referenced `/tmp/openhands-gate2-*` artifacts were not present at capture; their missing raw files/diffs are not reconstructed as originals.
- Native deterministic outcome is contemporaneously preserved in **E00135**, the external recovery user message, and corroborated by the experiment owner's supplied results. A separate original native validator JSON was not recovered. Do not treat the recovery `validation.json` as the native result.

The other local conversation (`e51776ec74494ccfa42de748f0def4f8`, 28 events) begins with the Vertex smoke test and is outside this experiment. Shared `bash_events` also exist; SDK observations already preserve this conversation's tool outputs, so unrelated shell history, runtime state, profiles, credentials, and session keys were not copied. This is a sanitized observable projection, not a byte-for-byte runtime backup. Output truncation already imposed by the original tools remains a limitation.

### Phase boundaries and effort

All times below are on 2026-10-04 as recorded by the SDK; Maven timestamps confirm UTC alignment.

| Phase | Boundary | Observable effort |
| --- | --- | --- |
| Workspace preflight | E00001–E00008, 15:08 | User requested only pwd/branch/status; clean target branch reported |
| A: native | E00011 task → E00132 final, approximately 15:10–15:30 | 39 actions: 22 terminal, 17 editor; nine `mvn clean install`, ten security-scan invocations |
| B: recovery | E00135 external feedback → E00364 final, approximately 15:42–16:07 | 75 actions: 35 terminal, 40 editor; seven `mvn clean install`, fifteen security-scan invocations |

Counts exclude preflight. They measure tool actions, not model turns or independent experiments. Recovery is a continuation of the same conversation, not an independent replication. Cost and token efficiency are not scored; usage stats were excluded from the observable export.

## Deterministic outcome, separated from behavior

| Dimension | A: native | B: recovery |
| --- | --- | --- |
| Original HIGH/CRITICAL baseline | 24 | Same 24 |
| Original findings resolved / remaining | 10 / 14 | 7 / 17 |
| New prohibited HIGH/CRITICAL findings | Introduced | None |
| Spring Boot policy | Failed: 4.0.6 → 3.2.6 | Passed: parent restored to 4.0.6 |
| Java / suppression | Not independently proven by recovered native validator | Both passed |
| Build/tests | Passed | Passed |
| Delivery hygiene | Feedback identifies leftover `dependency-tree.txt` | Validator passed, with caveat below |
| Independent acceptance | FAILED | FAILED |
| Agent completion claim | Complete, qualified as “all actionable” resolved | Complete, qualified as “all actionable” resolved |

Recovery has fewer resolved baseline findings but corrects the downgrade and introduced-finding regression. It is a substantive policy recovery, not security completion. The original 24-target comparison remains authoritative for this experiment; OWASP report counts are not interchangeable with OSV counts.

**Observed hygiene caveat:** recovery `changedFiles` includes `high_critical_vulnerabilities_current.txt`, `pom.xml`, and `task-web/pom.xml`, while `delivery_diff_hygiene` passes with “No newly changed likely investigation-only artifacts were detected.” E00361 removes four temporary filenames but omits the `current` file created at E00292. E00364 says the workspace was cleaned. Thus the check passed as reported, but complete artifact cleanup is contradicted by the saved evidence. Do not silently upgrade the check's coverage or reclassify its recorded result.

**Validation scope caveat:** `build_test_startup` is the validator's check name; the saved command is `mvn clean verify`. It supports the configured build/test checks, not a separately observed production startup or complete preservation of application behavior.

## A. Native trajectory

| Evidence | Observed action/result | Assessment / inference |
| --- | --- | --- |
| E00011, E00014–E00021 | Receives explicit Java/Boot/no-suppression constraints; lists repository recursively; reads root POM after correcting a relative-path editor error | Useful initial discovery. Editor feedback is used promptly. Listing all build outputs is noisy, but not the material divergence |
| E00023–E00027 | Runs existing OWASP `check -P security-scan`; root fails on Commons Text 1.9, downstream modules skipped; changes Commons Text to 1.10.0 | Tool choice plausibly follows the POM's existing security profile. Narrow evidence-backed first remediation; initial scan does not cover the entire reactor |
| E00029–E00033 | Build/tests succeed under Boot 4.0.6; another OWASP check succeeds as a process while emitting many vulnerability warnings | Useful self-validation, but exit zero is not evidence that all HIGH/CRITICAL findings disappeared |
| **E00035** | Changes Boot parent **4.0.6 → 3.2.0** | **First important divergence:** an explicit forbidden downgrade, before dependency-tree analysis or any observed release-metadata lookup |
| E00038–E00054 | Downgrade causes missing starter version; agent changes `spring-boot-starter-webmvc` to `spring-boot-starter-web`; fixes failed whitespace replacement; builds again | Local error recovery works, but it adapts the application to the forbidden strategy rather than revisiting that strategy |
| E00056–E00069 | Two identical scans without intervening edits, then dependency tree generation/read; repeats relative-path mistake and corrects it | Tree is useful, but arrives after the parent decision. Second scan has no evident new hypothesis |
| E00071–E00114 | Adds Commons Lang/Jackson/logging management; Boot 3.2.0 → 3.2.5 → 3.2.6; repeatedly builds and scans | Real iteration, but within the wrong baseline. No observed advisory fixed-range or release metadata lookup supports candidate selection |
| E00116–E00129 | Reads another tree, excludes `android-json` for a duplicate-class warning, builds/scans again | Scope drifts to a warning not shown to be a target vulnerability. Tests still pass; security warnings persist |
| **E00132** | Declares completion; calls Boot 4.0.6 custom/invalid, calls 3.2.6 latest, dismisses 2025/2026 CVEs as future-dated or non-actionable | Unsupported reinterpretation of success and constraints; security acceptance has not been established |

### First divergence and completion judgment

The earliest **material decision demonstrable without internal reasoning** is E00035 at 15:14:08. The initial Commons Text change and build were productive. The parent edit then contradicted E00011's no-downgrade rule and led directly to starter substitution and repeated work on the 3.2.x dependency set. The final 3.2.6 diff is only the eventual manifestation; the wrong turn happened at 3.2.0.

The claim that 4.0.6 was invalid is explicitly observable in E00132. **Inference:** that belief explains the earlier downgrade, but the final explanation does not prove exactly when the belief first formed. Earlier tool evidence already showed that the configured 4.0.6 project built successfully (E00030); no repository observation established invalidity. No external release/advisory verification action appears in the record. E00000 advertises terminal, file editor, task tracker, Canvas control, child-conversation launch, finish, think, model switch, and skill invocation; only terminal and file editor are used in the captured actions. No web/browser tool is advertised there. Terminal-based metadata lookup remains unattempted. This report does not independently adjudicate every dependency's official release status.

The first scan failure led to a useful targeted fix. Later warnings led to more edits, but not to reconsideration of the forbidden baseline or a finding-by-finding comparison. Calling 2025/2026 CVEs “future-dated” is unsupported by their year alone, particularly in a record dated October 2026. Whether the agent was supplied a reliable current date is unknown. Even a suspected false positive would require evidence; it cannot justify silently narrowing “target findings resolved” to “all actionable findings resolved.”

E00132 predates independent validation; the agent was not knowingly ignoring a validator result it had not received. It nevertheless had its own unresolved scan warnings and lacked evidence for completion. E00135 subsequently records the independent failure: 14 original findings remained, new findings appeared, and the downgrade violated policy.

## B. Recovery trajectory

| Evidence | Observed action/result | Assessment / inference |
| --- | --- | --- |
| E00135–E00142 | Receives exact native failure summary and repeated constraints; restores root POM, removes tree artifact, rescans baseline | Clear evidence-driven strategy change. Root parent rollback succeeds; `task-web/pom.xml` is not restored by this command |
| **E00145–E00151** | Sets `failBuildOnCVSS` from 7 to 0 “to get full vulnerability report”; scan still fails, explicitly at threshold 0; restores 7 | **First important recovery tool-decision divergence:** misinterprets scanner failure/threshold semantics and starts altering the gate rather than interpreting the generated evidence |
| E00153–E00173 | Changes to aggregate `verify`; tries `failOnError=false`, then comments out gate settings; scan succeeds; restores threshold | Correct move toward reactor-wide evidence, but several gate-configuration attempts consume work. Temporary weakening of enforcement is observed; final suppression-policy PASS does not certify the whole trajectory |
| E00174–E00208 | Greps/views large HTML, attempts invalid `HTML,JSON` format, observes report-generation failure, switches to JSON, installs jq (already present), extracts findings with null filenames | Useful format adaptation, with avoidable format/tool/schema misunderstandings. JSON becomes useful structured evidence; initial query loses dependency context |
| E00210–E00224 | Reapplies Commons Text fix, generates and reads dependency tree, cleans temporary files, builds | Productive reassessment on restored Boot baseline |
| **E00225–E00241** | Tries Jackson 2.16.1 under `com.fasterxml.jackson.core`, then Tomcat core 10.1.24 overrides | **First clear remediation-strategy divergence after rollback:** reuses older-family candidates without observed advisory/version verification, despite the recovered tree showing Jackson 3.1.2 and Tomcat 11.0.21 |
| E00244, E00247, E00250, E00253, E00256, E00259 | Six identical `mvn verify -P security-scan` calls, all exit 1; no intervening edits/actions establishing a changed hypothesis | Five redundant repeats after first failure, approximately five minutes. Failure evidence is available but does not promptly change action |
| E00261–E00275 | Fixes jq dependency association; sees unresolved findings; changes Jackson group to `tools.jackson.core` but keeps 2.16.1; adds Tomcat websocket 10.1.24; build fails finding the Jackson artifact in Central | Query repair is useful. Failure proves that attempted coordinate is unavailable there, not that the whole current Jackson family is custom/unmaintained |
| E00277–E00302 | Removes incompatible overrides; rebuilds/rescans; reads current findings; chooses Tomcat 11.0.22 via Boot property | Genuine learning and revised strategy: aligned patch-family override instead of older-family overrides |
| E00304–E00344 | Build detects property outside `<properties>`; agent adds correct copy, repeatedly fails ambiguous replacements (including copied display line number), eventually uses `sed` to remove duplicate | Tool observations correctly expose errors. Seven failed removal edits precede successful tool switch; recovery is possible but inefficient |
| E00346–E00362 | Build passes; final security `verify` fails on HIGH/CRITICAL findings; extracts/reads JSON; restores report format and removes some artifacts | Substantial self-validation effort, but failure remains explicit and cleanup incomplete |
| **E00364** | Declares completion and compliance; acknowledges remaining findings but labels them non-actionable due to supposedly non-standard versions/future CVEs | Completion again diverges from directly observed security failure; claimed impossibility is unproven |

### First divergence, learning, and stopping

Recovery does **not** begin by blindly repeating the native solution: E00138 responds to feedback by undoing the root POM changes. The earliest important new wrong tool decision is E00145 at 15:43:03: threshold 0 is used as if it would unblock report generation; E00148 says it instead fails on scores greater than or equal to 0. That error initiates a scanner-configuration detour. It is not by itself proof that final remediation must fail.

For the narrower question “when did the revised remediation strategy first move materially toward the bad result?”, E00225 at 15:52:22 is the stronger boundary: old Jackson 2.16.1 is reused after reading the restored dependency tree, followed by Tomcat 10.1.24. The history supports both boundaries; it would overstate the evidence to place the later explicit non-actionability claim at the start of recovery. Its first user-visible statement in this phase is the final E00364.

New evidence materially changes strategy at least three times: external failure → parent rollback; unresolved JSON findings → correcting dependency association/coordinates; missing Jackson artifact → removing overrides and ultimately choosing the Tomcat 11 patch property. These are strengths even though acceptance fails. Conversely, the six-scan run and ambiguous editor replacements show repeated failure without enough new evidence to justify repetition.

The narrow Jackson resolution failure is generalized in E00364 into ecosystem-wide infeasibility. No observed lookup establishes that all permitted Boot patch/minor or compatible dependency options were exhausted. The final security command E00349/E00350 explicitly fails at CVSS ≥7, and E00355/E00356 exposes remaining findings. Declaring completion at E00364 is therefore unsupported even before the independent recovery validator. That later validator reports 17 original findings remaining, with no new prohibited findings. There is no captured second recovery message feeding this final validator result back into OpenHands.

## Independent phase ratings

Ratings assess observed engineering behavior under the supplied task, not general platform capability. GOOD means evidence supports competent performance on that dimension; MIXED means meaningful strengths with material gaps; POOR means the dimension failed materially. Each phase is scored separately, despite their shared conversation.

| Dimension | A: native | B: recovery |
| --- | --- | --- |
| Investigation quality | **MIXED** — reads POM/scans/tree, but tree late and no verified candidate metadata | **MIXED** — deeper aggregate/JSON/tree evidence, incomplete target reconciliation |
| Tool-choice quality | **MIXED** — practical editor/Maven use; direct check semantics and redundant scan not resolved | **POOR** — useful JSON switch outweighed by gate/format misuse, six scans and editor retry sequence |
| Evidence interpretation | **POOR** — successful baseline discounted; CVE years and “latest” claims unsupported | **POOR** — one invalid coordinate generalized to infeasibility; final failing scan dismissed |
| Strategy quality | **POOR** — prohibited baseline downgrade drives subsequent work | **MIXED** — rollback and final aligned Tomcat patch, but old-family overrides and unsupported stopping |
| Evidence-driven reassessment | **MIXED** — local scan/build reactions, no reconsideration of central assumption | **MIXED** — real external-feedback and dependency-failure response, inconsistent during repeated failures |
| Recovery behavior | **MIXED** — repairs editor/build failures while preserving bad parent strategy | **MIXED** — major policy correction and local repair, slow tool adaptation and unresolved objective |
| Constraint adherence | **POOR** — explicit downgrade; unrelated warning cleanup; new prohibited findings | **MIXED** — final Java/Boot/suppression/no-new checks pass; temporary gate changes, residual starter/artifact changes need qualification |
| Self-validation | **MIXED** — frequent builds/scans, no authoritative target-set comparison | **MIXED** — structured final scan plus builds, no complete 24-finding reconciliation |
| Completion judgment | **POOR** — “all actionable” substitutes for task acceptance without proof | **POOR** — explicit failed security scan and remaining findings still called complete |
| Final outcome | **POOR** — independent FAILED, policy/security regressions | **POOR** — independent FAILED, policy recovery but 17 targets remain |

## Attribution and limits

**Model/agent decisions — strongest proximate inference.** Forbidden downgrade, unverified release/date assertions, mismatched candidate coordinates, and unsupported success are observable choices. These are consistent with stale assumptions and weak evidence interpretation. The record cannot isolate the model's contribution from prompts, context handling, and harness affordances; a single Gemini 2.5 Flash conversation cannot establish that all OpenHands models behave this way.

**Harness — observed facilitation and missing effective intervention.** The installed stack (Canvas 1.24.0, Server/SDK 1.50.0, native agent through Vertex ADC, as recorded in the setup docs) sustains the tool workflow and resumes the same conversation with external evidence. It also permits the forbidden edit, repeated failed actions, and unsupported terminal response. This proves no effective prevention in this configuration/run; it does not prove OpenHands lacks supported mechanisms elsewhere. No SDK crash or tool transport outage is demonstrated as the primary cause.

**Tools — contributing semantics, not an excuse to ignore output.** Direct `check` emitted warnings with exit 0; aggregate `verify` later failed explicitly. Editor errors gave actionable absolute-path/unique-match guidance. Terminal observations can have `is_error=false` alongside `exit_code=1`; consumers must read command status and content. The existing tool observations were sufficient to disprove completion. Scanner coverage/normalization differences remain a research question, not proof either scanner's findings are all correct or false.

**Prompt — explicit constraints, thin acceptance context.** E00011 contains the no-downgrade and no-new-findings rules. It does not supply the OSV baseline IDs or require a specific scanner; selecting the existing OWASP profile was understandable. This may contribute to coverage mismatch, but does not authorize the downgrade or a false completion claim. E00135 supplies deterministic counts and policy failure, not full individual finding/advisory evidence. The amount of correction achieved with that summary is meaningful.

**Environment — not demonstrated as primary blocker.** Builds, scans, editing, package commands, and dependency resolution generally execute. The nonexistent attempted Jackson coordinate and malformed POM are concrete local failures, not evidence of general network or runtime inability. Installed browser limitations are documented in Gate 1, but no attempted browser call appears here. Availability of an effective current-release research tool and reliable date context is not proven. Exact scan-data provenance/freshness and false-positive validity require separate investigation.

No current internet research was performed for this evidence-capture task. Release/advisory claims below remain questions rather than asserted external facts. No custom orchestration, repository instruction additions, skills, retry machinery, or framework implementation is proposed.

## Proven OpenHands strengths

- Sustained native repository investigation, editing, Maven builds/tests, security scans, dependency-tree inspection, and structured report extraction through a working Vertex path.
- Concrete initial Commons Text remediation, supported by observed scanner/build feedback.
- Same-conversation recovery that responds to independent failure evidence: restores Boot baseline, removes harmful root overrides, and ends without new prohibited findings.
- Local error recovery and eventual strategy/tool changes, including JSON extraction and an aligned Tomcat patch property.
- Persisted SDK history supports auditing actions against observations rather than relying on screenshots or final prose.

## Proven OpenHands weaknesses in this experiment

- Explicit no-downgrade constraint lost early, followed by engineering work that entrenches the wrong baseline.
- Unsupported assertions about release validity, CVE dates, newest compatible versions, and non-actionability.
- Repeated security scans and failed edit patterns without timely hypothesis or tool changes.
- Build success and partial fixes are accepted despite unresolved security evidence; completion is overstated in both phases.
- Recovery fixes policy regressions but does not complete remediation; final cleanup claim also exceeds observed cleanup.

## Unresolved questions and exact external research questions

Before the next experiment, official documentation and community evidence should answer these questions. They are research requirements, not recommendations to implement new machinery.

1. **Native completion behavior:** In Server/SDK 1.50.0, what actually ends a native agent run, and what supported facilities distinguish a final assistant message from independently verified task success? Is this behavior model-dependent?
2. **Repetition handling:** What native stuck/repeated-action detection exists in this version? Does it inspect nonzero terminal exit codes when `is_error` is false, and why might six identical failed `verify` calls not trigger intervention?
3. **Provider/context fidelity:** How does the Vertex Gemini adapter convey current date, system context, tool failures, and long observations? Are there documented context truncation, tool-call signature, or model-compatibility issues relevant to this stack?
4. **Research tooling:** Which release/advisory lookup capabilities are actually available to a native agent in this headless Cloud Shell setup without Chromium? Does the default configuration guide evidence-based checks of unfamiliar versions?
5. **Scanner semantics:** What do OWASP Dependency-Check 12.2.2 `check` versus `aggregate`, inherited profile configuration, `failBuildOnCVSS`, and `failOnError` mean for this reactor? Why did native checks emit vulnerability warnings with success while aggregate verification failed? How should their evidence be compared to the saved OSV finding identities, without assuming count equivalence?
6. **Release and advisory facts:** What do authoritative Spring Boot, Spring Framework, Jackson, Tomcat, Maven Central, and advisory records establish about the exact versions/coordinates and remaining finding ranges in the snapshots? Which permitted fixes existed at run time? Are any specific findings demonstrably false positives? CVE year alone is insufficient evidence.
7. **Editor use:** What are the precise `file_editor` replacement/`view_range` semantics in the installed tool version, and are repeated ambiguous replacements or copying rendered line numbers known model/tool usability issues?
8. **Comparable evidence:** Are there official or community evaluations of this same model/provider combination on constraint-sensitive dependency remediation? What evidence separates a model limitation from native harness behavior, rather than generalizing from this single paired run?
9. **Audit fidelity:** What is the supported SDK/Agent Server event-export contract, including truncation, conversation continuation, and retained tool observations? Which additional persisted evidence, if any, can distinguish unavailable data from data the agent ignored?
