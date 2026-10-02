# Autonomous Agent — Work State

**Updated:** 2026-10-02. **Repository:** `AILearner365/oss-remediation-adk`, branch `context-hygiene-clone-challenge-before-commitment`. This is a development conversation bookmark, not an agent runtime checkpoint. Read [PROJECT-DIRECTION](PROJECT-DIRECTION.md) for the stages and IDs.

## Active stack and return point

1. **Main objective:** reliable, general autonomous problem solving, first evaluated on OSS remediation.
2. **S3 / P1:** engineering decision quality varies; a valid remediation can still reflect premature elimination of a better project-native control point.
3. **P1.1:** evaluate the frozen Challenge Before Commitment behavior at Q5 using the [experiment record](../EXPERIMENT_1_CHALLENGE_BEFORE_COMMITMENT.md), baseline `e92837d`.
4. **P2 support work:** remove independent harness/tool/capture contamination before judging P1.1.
5. **P2.1 — resolved for now:** explicit whole-file delete capability replaced ambiguous text-delete semantics.
6. **S4 current follow-up:** reconcile the three newer workspaces at `1dd959f4`: incomplete-read reconstruction, Outcome/check freshness, Final Resolution reconciliation, and multi-cycle capture recovery. Prior research, scanner, typed capture, shared retry, retention and phase-toolset work remains in place.
7. **P2.4:** `005510` demonstrates two successful retained-output reads; the decisive correction fact came from a later filtered shell command. Outcome retained-evidence use is a new live check.
8. **P2.2 / P2.3:** `011600` demonstrates experimental runtime-resource scanning before Intent and three unknown-call corrections followed by Intent accepted on attempt 4. Scanner transition repair and tenth-attempt boundaries have separate acceptance scopes.

**Current return point:** the branch bookmark at `bd1d87b0` was reconciled with head `1dd959f4`, which adds three live workspaces. Focused harness fixes are implemented in the working branch; see the new batch audit below and the final commit for offline results. Next perform a small live acceptance check, separately restore/revalidate PR #203's security-scan profile in the target repository, then return to comparable frozen P1.1 reasoning evaluation. No paid/live model run or delivery operation was started for this implementation task.

## New three-workspace audit and focused harness follow-up

`024556` and `025247` each captured complete one-cycle Outcomes, passed independent validation and delivered Draft PRs; `030451` reached three cycles, with cycle-1 Intent capture exhausted, cycle-2 complete capture but three remaining findings, and cycle-3 complete capture and passing validation. Its accepted cycle-3 Outcome was `PARTIALLY_REMEDIATED`, so automatic delivery remained ineligible even though deterministic target comparison passed. The final result's `FULLY_VALIDATED` is the separate validation-derived classification, not a rewrite of that Outcome.

**Confirmed file-loss mechanism:** `025247` repeatedly read only the first ~8,000 characters of the root `pom.xml` (`moreExists=true`, continuation at line 175 or 180). The saved interaction-70 `old_text` is byte-for-byte the 7,963-character partial read content; its replacement supplied an 8,313-character reconstructed XML prefix. After further partial reads, `edit_workspace_text(action="write")` accepted that reconstruction as the entire existing file without requiring the unseen tail. The final diff removes the unrelated `security-scan` profile and its OWASP Dependency-Check/CycloneDX executions. Build and OSV checks passed but did not cover preservation of that profile. The Outcome request already contained the complete final diff (`diffComplete=true`); the accepted model text nevertheless claimed only dependency/version changes and called pre-Intent parent experiments deviations from an Intent that already selected targeted overrides. This is demonstrated model misdescription despite available evidence, not proven context loss.

**Protection:** read responses now distinguish a complete requested excerpt (`complete`) from `fileComplete` and cumulative `readCoverageComplete` for the current file revision. Existing-file `write` requires a receipt issued only after all lines/columns of that revision have been returned by the read tool, including multiple ranges; a stale receipt fails after content changes. A replacement of the exact partial excerpt is rejected with guidance to use a narrower targeted span or complete-read rewrite. Ordinary exact-span `replace` preserves all text outside that span; explicit `delete_workspace_file` and fully read, intentional rewrites remain supported. The receipt proves tool exposure of bytes, not human/model comprehension or appropriateness of deletion. Shell-based edits and model-provided narrower but overbroad replacement spans remain outside this protection; validation still checks only its configured properties.

**Outcome and validation:** current authoritative change evidence now includes captured time, tree digest, net line additions/removals with bounded excerpts and a full diff reference. Outcome also receives the accepted Intent, historical previous-cycle validation with its evaluated tree, and cycle/workspace/time-labeled observations. A scan before a later authoritative action is labeled historical; no current-cycle self-scan after the latest action is stated explicitly. The check's repository digest is not known for ordinary shell/self-scan observations, so the harness does not claim those are current-state proof. The model still writes rationale, reassessment and arbitrary coverage prose. Final Resolution leads with latest deterministic validation facts and appends explicit reconciliation against the historical accepted Outcome, including the partial-versus-passing contradiction; the accepted section remains append-only. Existing delivery policy rejects a passing validation paired with `PARTIALLY_REMEDIATED`, preserving manual review rather than silently promoting the model status. A policy decision would be needed to automate delivery in that state; this batch does not make it.

**Capture recovery:** `run_capture_status_for()` previously required every prior cycle to have a failed capture flag, so cycle 2's complete capture blocked recovery of cycle 1 after a complete, passing cycle 3. It now evaluates only earlier non-complete captures against the existing failed-capture plus validation conditions; historical warnings and cycle records remain. A missing unaudited capture, late Intent, or non-passing latest validation remains non-recovered. Capture quality, engineering validation and delivery eligibility stay separate.

**Unknown-tool investigation:** `030451` cycle 1 made three batches of invented `SubmitCycleIntentAnswers`, `SubmitCycleIntentAnswersEvidence`, and `google:python_interpreter`, then a tenth unknown call; feedback listed registered phase tools including `submit_cycle_intent`, but the model repeated the invented names. `011600` had recovered after three unknowns on accepted attempt 4. The registered declaration has typed `section`/`answer` Intent items, and the actual correction names the available tool. The trace proves retry exhaustion and ineffective recovery for this session, but not that schema ambiguity caused the model's repeated names. No alias, Python wrapper, allowance expansion or session redesign was introduced.

**Research/scanner classification:** the new blocked DuckDuckGo searches were classified as bot challenges; later Maven Central XML fetches succeeded. Large HTML acquisition was not exercised. `025247` used experimental runtime resources and then omitted that argument on authoritative scans; it did not exercise authoritative argument rejection/retry. None of the three runs called `retrieve_retained_evidence`; Maven metadata retained version data beyond the shown 4,000-character excerpt, but acquisition alone did not mean the model used those bytes. No search or scanner call is made mandatory.

**Separate target remediation:** Draft PR #203 contains the deleted security-scan profile. Restore the OWASP Dependency-Check and CycloneDX executions in the target repository/PR, then rerun its security-profile verification, build and independent vulnerability validation before review/merge. This harness task does not edit or merge that target repository.

**Small live acceptance after this offline change:** run one controlled model case with a generic multi-section file whose first read is incomplete; verify continuation metadata, rejected excerpt replacement/receipt-less whole write, successful narrow edit preserving the tail, and an intentional full-read rewrite if chosen. In a separate two- or three-cycle case, check that Outcome receives accepted Intent, line removals and prior-cycle validation marked historical; after a corrective edit without self-scan, verify no claim that old findings evaluate the edit, latest deterministic result appears in Final Resolution, and a stale partial Outcome still requires manual delivery. Inspect `capture_classified`, `capture_warnings`, and delivery eligibility separately. Keep Experiment 1 at **CONTINUE** until these boundary checks and comparable reasoning runs are assessed.

**Offline verification:** the active unit suite passed 180 tests (2 skipped); focused read/edit, capture, Outcome and Final Resolution regressions passed; `compileall` and `git diff --check` passed. A 227-test run covering the active harness plus one mistakenly included legacy outcome-summary module had six errors, all in that disabled old entry point, with no active-harness failure. The exact 221-test active-harness rerun had one time-budget-sensitive integration failure (`test_execution_failure_still_requests_outcome_and_runs_validation` returned `EXECUTION_LIMIT_REACHED` under the slower run); that test and three focused regressions passed immediately on isolated rerun. The broad 292-test discovery run also failed old `oss_remediation_agent` phase tests. These broad/legacy failures are recorded rather than claimed as clean. No paid/live model, benchmark or real delivery was run.

## October 2 live evidence and focused follow-up

Reconciled head `02dd9642` contains the prior `d0bac2e9` retry/chronology fixes and three new live workspaces. All three used target `9ea1b0ed5ca255db0fc7c659d050896d3ed5db78`, `gemini-2.5-flash`, and `max_returned_output_chars=3000`; each completed one cycle, resolved 24/24 target findings, passed independent deterministic validation, and delivered Draft PR #199 (`005510`), #200 (`010355`), or #201 (`011600`). The older open-acceptance descriptions below are historical and are superseded only to the extent established here.

- `011600`: one ADK session received three unknown-call corrections and accepted Intent on shared attempt 4. Before Intent, a HOME-based runtime resource reached the experimental scanner, which reported 8 findings and then clean after revision. This establishes that experimental handoff path and same-cycle unknown-tool recovery, not tenth-attempt exhaustion.
- `005510`: truncated shell output led to two successful retained-evidence reads (offsets 0 and 4000). A later filtered `mvn dependency:tree | grep jackson-core` response supplied the decisive `tools.jackson.core:jackson-core:3.1.2` fact. Retrieval was exercised, but the trace does not show retrieval alone driving the correction.
- `010355`: accepted Intent and attempted authoritative `4.0.6 -> 3.2.6` despite `allow_downgrade=false`, rationalizing the actual version as an assumed placeholder/equivalent. Later reversal and compliant delivery do not validate that earlier reasoning. P1.1 remains **CONTINUE**; Q1–Q5 and Challenge Before Commitment semantics are unchanged.

### Confirmed causes and uncertainty

Research: all six retained DuckDuckGo search pages contain the challenge form and human-verification text. `_retrieve` treated the HTTP body as acquired; `_SearchParser` found no result anchors and returned generic extraction failure. The Spring project fetch retained exactly 100,000 bytes, ending in CSS before the body; extraction yielded no text. Source truncation was recorded but recovery information did not explain that retained retrieval could not recover the missing tail. These failures withheld useful external evidence; they do not justify unsupported Spring/Jackson assumptions or prove that acquisition success would have changed the model's reasoning.

Outcome: `005510` tool interactions 62–65 show the filtered dependency evidence and correction from `com.fasterxml.jackson.core` back to `tools.jackson.core`; `validation/cycle-1.diff` confirms the final state. The accepted Outcome (interaction 73) describes the earlier opposite change as the successful correction. The same session had the correct evidence. Its Outcome request contained changed filenames and command/edit metadata, but no final diff or command output; repository/evidence retrieval was unavailable in Outcome. The journal checked structure and lifecycle, not arbitrary prose facts; chronology rendered paths and tool names, not final values. These are demonstrated grounding limits. Why the model selected the stale narrative is uncertain; it is not established as context loss or a harness rewrite. Delivery used the earlier execution response, while accepted Outcome answers fed final-resolution approach history and future-cycle journal context, allowing stale claims to persist.

Scanner: after Intent, `active` selected the authoritative workspace but any supplied runtime path still entered the experimental resolver. That resolver correctly rejected authoritative access with the misleading generic “Current-cycle experimental runtime is unavailable” error. The interface did not state the supported authoritative retry. Independent scanning succeeding later establishes availability in that validation environment, not that either rejected invocation actually ran a scan.

### Implemented boundary changes

Research now classifies known challenge pages and HTTP 403/429 as blocked, retains provenance/raw bytes and explicit acquisition metadata, and distinguishes source-limit-before-usable-content from extraction and network failures. The default source bound is 2,000,000 bytes, with a hard cap and explicit prefix completeness; scripts/styles are excluded from extracted text, allowing body content beyond the old small prefix when within the cap. Recovery advises supported accessible sources or uncertainty, without bypassing challenges, replacing providers, adding credentials, or prescribing domain research. Challenge detection is conservative and larger/dynamic pages can still be unusable.

Outcome receives a current authoritative net-diff snapshot plus bounded workspace-separated command/scan observations and retrievable full artifacts. The accepted record, delivery summary, and replacement-session reference index preserve these facts separately from model explanation. Retained-artifact retrieval is permitted in Outcome while repository execution remains gated. Only the reliably verifiable no-change-status/nonempty-diff contradiction adds rejection, with specific evidence and the existing retry counter. No string matcher claims to validate arbitrary prose; semantic reassessment remains model-owned.

Scanner declarations, post-Intent feedback, and argument errors now say `runtime_resource_path` is experimental-only. An authoritative call with that parameter is rejected before resource resolution and advised to retry `scan_current_repository(workspace='authoritative')` with the parameter omitted. No supplied path is ignored, no experimental resource is silently reused, and path isolation checks remain.

### Offline checks and small live acceptance procedure

Focused offline tests cover challenge/raw retention, HTTP/network versus extraction failure, a large style/script prefix followed by body text, a cap reached before body, partial useful content, actual capability response metadata, final correction versus stale execution summary, retained Outcome evidence, delivery-summary grounding, objective no-change repair, ADK Outcome tool exposure, and scanner rejection followed by the supported authoritative retry. The final combined run passed **217 tests, 2 skipped**, across `test_research_acquisition`, `test_autonomous_capabilities`, `test_decision_journal`, `test_autonomous_prompt_continuity`, `test_intent_tool_recovery`, `test_autonomous_agent_runtime`, `test_autonomous_scanner_constraints`, `test_autonomous_validation_delivery`, `test_autonomous_xray_scanner`, and `tests.integration.test_autonomous_orchestrator`. Initial regressions exposed an omitted execution-continuation fact (restored) and an old test expecting acceptance of a no-change claim despite real changes (updated to verify bounded rejection and continued cycle recovery). A final 30-test journal and Outcome integration check also passed after clarifying the snapshot capture-time label. Offline replay of all six saved search raw responses returned `blocked/BOT_CHALLENGE`. `git diff --check` passed. Historical run evidence is untouched, and no live model/scanner or real delivery operation was started.

On the live-run machine, use small controlled exercises on this fixed harness revision (no general benchmark prerequisite):

1. Fetch an accessible HTML page with a large head and confirm useful body text, raw/extracted references, acquired byte count and completeness. If the search provider returns a challenge, confirm `blocked/BOT_CHALLENGE`, empty usable results, retained raw evidence and actionable guidance; do not solve or bypass it. Inspect an intentionally bounded source separately to confirm its missing tail is not advertised as retained.
2. Make a temporary configuration edit, correct it, and run a relevant check. At Outcome, inspect the supplied authoritative net diff and workspace-separated observations; retrieve any omitted evidence and confirm the model's accepted account explains the final correction. A no-change contradiction should return the current diff reference and accept a corrected report within the shared allowance. Free-form prose still requires review against evidence.
3. Build with a current-cycle experimental runtime resource, scan experimentally, accept Intent, then verify that an authoritative scan with that argument gets the explicit omission guidance. Retry without it and confirm an actual authoritative scanner result, without experimental cache reuse. Keep independent validation separate.

These fixes still require live model use of the new guidance and Outcome evidence, and real network/scanner acceptance in the deployed environment. Provider replacement, if desired because challenges persist, is an explicit supported-API/credentials/cost dependency. After these targeted checks, return to comparable P1.1 runs on the same target/configuration; score task success, capture quality and decision quality separately.

## October 1 review of `2511ad81`: retry and Outcome chronology

The reviewed head already contained the typed Intent API, partial draft repair, phase toolset, research retention and scanner behavior. Two narrower defects remained. The unknown-tool callback checked a combined count only when an unknown call occurred, while journal rejection accounting and the orchestrator used separate counts. Nine unknown calls followed by one rejected Intent could therefore leave a later valid submission open. Outcome chronology mixed experimental and authoritative observed actions without rendering their `workspaceKind`.

Each Intent or Outcome checkpoint now has its own ten-attempt counter per cycle. Each unknown ADK invocation in that phase and each checkpoint submission consumes one attempt, regardless of order. A valid submission can succeed on attempt ten and is not a rejection; an unknown call or rejected submission on attempt ten reports `retryAllowed: false`. A later valid submission is blocked. The callback, journal and orchestrator use the same count, and trace events record admitted and blocked attempts. Outcome uses the same rule because its phase also permits unknown-tool recovery followed by `submit_cycle_outcome`; execution-phase unknowns remain separately bounded. The harness renders observed Outcome actions with workspace tags and leaves material rationale and reassessment to the model.

Focused ADK and journal tests passed (38 tests); the broader relevant suite passed 90 tests with 2 skipped. `git diff --check` passed. ADK tests cover both mixed orders, success at the tenth slot, immediate exhaustion, and no authoritative edit before accepted Intent. A focused journal test checks experimental and authoritative edit/build tags in accepted Outcome text. These are offline checks, not a live model acceptance claim. On the live-run machine, inspect a cycle's unknown call → callback correction → rejected Intent → valid Intent accepted within the remaining allowance → authoritative edit, plus a final-slot invalid attempt with `retryAllowed: false` and a blocked later submission. Inspect an accepted Outcome containing both experimental and authoritative actions for the workspace tags. The separate retained-evidence and experimental scanner live questions remain open.

## October 1 responsibility-boundary reconciliation

Branch head before editing was `eb0e626b`. The code already had Intent-only unknown-tool feedback, a shared ten-attempt allowance, precise oversized-section feedback, and per-session interaction artifact names. Saved `022558` traces establish the original unknown-call and artifact-collision defects; earlier test reports establish only offline behavior. The remaining mismatch was exact Markdown parsing inside JSON, all tools advertised in every phase, Intent-only unknown-call recovery, prior-cycle source evidence omitted from replacement context, and `text/xml` rejected before extraction. The smallest coherent change keeps the one-agent loop, scanner and enterprise transport, and server-side gates while moving capture structure and chronology into harness-owned data/rendering. Historical journal text is not migrated in place. See the [journal API](../problem-solving-journal/README.md).

Focused tests cover typed capture, field repair, phase visibility in actual ADK model requests, unknown calls, no pre-Intent authoritative edit, retained evidence after failed capture, raw XML versus unsupported content, and older references through a manifest. The broader relevant suite passed 140 tests (2 skipped), and the final focused suite passed 77 (2 skipped). No paid/live model or real scanner run was started for this cleanup. The next live action is a small invalid/unknown call → correction → accepted Intent → authoritative execution trace, followed by a separate retained-evidence retrieval exercise. Live XML acquisition through approved network/proxy/TLS, model use of recovery references, and real experimental scanner handoff remain unverified. Neither architecture alignment nor offline tests establish improved engineering decision quality; frozen P1.1 remains `CONTINUE`.

## Post-fix implementation and runtime evidence

### October 1 P2.3 unregistered-tool failure

The prior bookmark preceded `3a415f61` (the `section`/`answer` contract fix) and `d931c3fc` (new saved runs). `run-20260929T022558Z-6343141c` shows cycle 1 calling unregistered `SubmitCycleIntentAnswers` and `google:python_interpreter` without an accepted Intent. ADK raised "Tool not found"; the orchestrator failed Intent capture and recreated the session after the cycle. In cycle 2, `submit_cycle_intent` was structurally rejected because `Concrete candidate solutions` exceeded 8,000 characters. A subsequent unregistered `google:python_interpreter` call again aborted the turn and lost that cycle. Cycles 3 and 4 later submitted accepted Intents. The older `run-20260928T011300Z-9fbd5b83` artifact is not present in this checkout; its reported invented Python call and 30,000-character output limit remain user-provided trace evidence rather than independently re-read artifacts here. Large payloads/retries correlate with the failures but do not prove why those tool names were generated.

ADK has a tool-error callback for missing registrations. The tested fix returns an explicit `submit_cycle_intent(cycle_number, answers=[{section, answer}, ...])` correction in the same ADK session without running or aliasing the invented call. Unknown calls and rejected submissions share the existing ten-attempt checkpoint allowance; exhaustion still fails capture and permits ordinary session recreation for a later cycle. Oversized-section feedback now states the actual length and how to shorten and resubmit via the registered tool. The saved trace references `agent/interactions/000001.json` from three different ADK sessions, so earlier payloads could be overwritten; interaction artifacts now use a per-session namespace to prevent that collision. This is harness behavior, not an engineering or Q1-Q5 change. Live model recovery remains unobserved.

### P2.1 — destructive editing
Commit `1eed9914881282e81f06da4aa62e116e2386e80a` implemented:
- `edit_workspace_text` write/replace only;
- text removal through replacement with empty string;
- explicit `delete_workspace_file` for whole-file deletion.

Latest live runs did not reproduce the earlier accidental root-`pom.xml` unlink failure. This is evidence that the specific ambiguity no longer appeared, not proof of global harness stability.

### P2.3 — Intent recovery
Commit `23e872b1a12f5290faa66d7600bc8d06c2fdf77c` removed the fixed “four identical validation errors → stop” rule. Targeted repair instructions remain; recovery is bounded by existing checkpoint turn/submission/time/model-call limits.

Live evidence:
- `run-20260928T010505Z-b4bbe021`: 2 rejected Intent submissions, then accepted.
- `run-20260928T014926Z-28562938`: 5 rejected submissions, then accepted and final success.
- `run-20260928T015654Z-1640abc0`: 1 rejected submission, then accepted and final success.

Conclusion: recovery works, but structural capture overhead can still be material. Treat this as cost evidence, not as engineering search depth.

### September 29 P2.3 capture-contract regression

On branch head `99694d45`, `run-20260929T011744Z-4982d887` made ten `submit_cycle_intent` calls across cycles 1–3. All 63 answer objects used `section` and `content`, with no `answer` key. The ADK declaration exposed each item as an arbitrary string map; the questionnaire named `section` but did not identify `answer` as the text key. Journal validation read only `answer`, reported empty answers, and the rejection guidance did not identify the key mismatch. Model continuations show it repeatedly tried to populate `content` and then treated the tool as broken. No Intent was accepted in four cycles, and the final reason was `CYCLE_INTENT_CAPTURE_INCOMPLETE`. This is capture/tool-contract contamination, not a clean P1.1 strategy outcome.

The narrow fix gives the ADK tool a required `section`/`answer` item schema, identifies a missing `answer` field in validation and repair feedback, and clarifies the questionnaire's submission shape. Focused and broader relevant tests pass. Substantive answers and Q1–Q5 reasoning requirements remain the model's responsibility. The previous post-fix successful captures remain evidence for those runs; they did not expose this variant of the interface failure. Live recovery from this specific malformed submission has not yet been observed.

### September 29 bounded-output evidence boundary

Both `011744` and `run-20260929T014035Z-52ad10a5` used a 3,000-character shell response limit. Respectively, 11 and 5 shell stdout responses were truncated, and each carried a retained stdout artifact/reference. Root `pom.xml` reads also exposed line continuation (4 and 11 responses with `moreExists`). Neither run called `retrieve_retained_evidence`. Source-file continuation and retained shell artifacts are distinct mechanisms. The traces do not establish that truncation caused either final outcome or that the retained-evidence recovery path works model-backed.

`011744` had no model engineering-scan calls; deterministic validation scans succeeded with 20 findings rather than failing. In `014035`, deterministic validation cycle 1 failed to resolve `org.springframework.boot:spring-boot-starter-webmvc:3.2.5` (registry 404), and correctly classified the scan as `INCOMPLETE_FATAL_FAILURE` / `DEPENDENCY_RESOLUTION`; validation remained `INCOMPLETE`, not clean. That scanner failure is separate from the `011744` Intent field mismatch and from the unobserved experimental handoff.

### P2.2 — runtime-resource handoff
The implementation supports `scan_current_repository(runtime_resource_path=...)` and declares each cycle’s experimental HOME/TEMP/logical `/tmp`. Integration coverage demonstrates a command-created current-cycle runtime directory can reach an experimental scanner consumer outside repository source state.

Live evidence remains incomplete:
- `run-20260928T010505Z-b4bbe021`: experimental Maven initially failed against `/root/.m2/repository`, then the model adapted to `-Dmaven.repo.local=/tmp/m2-repo` and reused that path for Maven commands. It did **not** call `scan_current_repository` experimentally before Intent. The only scanner call was authoritative after Intent and returned clean.
- `run-20260928T014926Z-28562938`: no pre-Intent scanner calls. After Intent, authoritative scans progressed 19 findings → 3 → 0 and the run delivered Draft PR #195.
- `run-20260928T015654Z-1640abc0`: no pre-Intent scanner calls. After Intent, authoritative scans progressed 3 findings → 0 and the run delivered Draft PR #196.

Therefore the exact acceptance path remains unproven:

```text
experimental edit/build
→ current-cycle Maven runtime resource
→ scan_current_repository(workspace="experiment", runtime_resource_path=...)
→ successful experimental scan
→ Intent
```

The missing evidence is **model choice/use and real end-to-end scanner acceptance**, not a known post-fix scanner wiring failure. The protocol does not require the model to use this scanner before Intent. An unattempted path cannot by itself turn an otherwise interpretable Q2–Q5 trace into a scanner failure. If an attempted experimental scan fails, inspect whether the cause is resource handoff, unusable dependency state, model invocation, or another condition. A confirmed capability failure that withholds decision-critical evidence contaminates the affected P1.1 inference and warrants separate P2.2 investigation. A model's failure to investigate a material uncertainty remains an engineering-decision question, judged against all reasonably available evidence mechanisms rather than scanner use alone.

## September 28 run outcomes (historical)

### `run-20260928T010505Z-b4bbe021`
- Cycle 1 completed successfully.
- Deterministic validation passed.
- Draft PR delivered.
- No Cycle 2 was expected because Cycle 1 reached validated success.
- No experimental scanner call before Intent.
- Reasoning still called Spring Boot `4.0.6` “custom or non-public” and eliminated parent upgrade on that basis.

### `run-20260928T011300Z-9fbd5b83`
- Final outcome: `PARTIAL / MANUAL REVIEW REQUIRED`.
- `cyclesCompleted = 2`, `captureStatus = INCOMPLETE`, `validationStatus = PARTIAL`, no delivery.
- Reason: configured operational budget reached.
- The model spent substantial effort on the unsupported premise that Spring Boot `4.0.6` was invalid/typo, attempted a `3.2.0` path, later reverted, and ended with remaining `spring-webmvc` findings. No PR was correctly created because full success was not validated.

### `run-20260928T014926Z-28562938`
- Final outcome: SUCCESS.
- One cycle; deterministic validation PASSED.
- Draft PR #195.
- Five rejected Intent submissions before acceptance.
- No pre-Intent experimental scanner call.
- Authoritative scan progression after Intent: 19 → 3 → 0 findings.

### `run-20260928T015654Z-1640abc0`
- Final outcome: SUCCESS.
- One cycle; deterministic validation PASSED.
- Draft PR #196.
- One rejected Intent submission before acceptance.
- No pre-Intent experimental scanner call.
- Authoritative scan progression after Intent: 3 → 0 findings.
- Reasoning was less destructive than earlier stale-prior traces: it treated `4.0.6` as intentional/custom and kept it, but still relied on an assumption instead of first establishing the parent’s actual management/control behavior.

## Reasoning-quality evidence still active

Do not conflate final success with decision quality.

Observed variance:
- Earlier and some newer runs treat Spring Boot `4.0.6` as non-standard/custom/invalid and use that assumption to eliminate or distort parent-level strategies.
- `011309` previously found `4.0.6 → 4.0.7` as a valid patch-level parent strategy and then reassessed from scanner evidence.
- `015654` preserved `4.0.6`, which is less harmful, but still did not establish decision-critical parent-management facts before commitment.

This keeps P4 / #18 / #22 / #25 active: stale-prior substitution, insufficient decision-critical investigation, and inconsistent synthesis of project-native control points.

## Harness-boundary evidence calls / insufficient-data question

No clean post-fix live trace yet establishes that the **retained-evidence retrieval path** was invoked specifically because a bounded harness response omitted decision-critical information. The recent runs primarily show direct read/search/shell use and authoritative scanning. Therefore do **not** claim that the harness’s “bounded response → retrieve retained evidence on insufficient data” recovery behavior has been behaviorally demonstrated by these latest runs unless a trace explicitly shows `retrieve_retained_evidence` or an equivalent recovery call driven by omitted evidence.

This remains a separate acceptance question from P2.2 scanner runtime-resource handoff.

## Historical return point (superseded by October 2 evidence above)

**Decision:** treat pre-Intent experimental scanning as an optional model evidence path, not a gate before frozen P1.1 evaluation. This does not claim live acceptance of the complete Maven/runtime-resource → experimental scanner → Intent path. The implementation and tests establish controlled handoff; four post-fix runs from target commit `9ea1b0ed5ca255db0fc7c659d050896d3ed5db78` contain no experimental scanner attempt before Intent. The frozen Experiment 1 protocol asks for decision-sufficient investigation and evidence-backed challenge, without prescribing a scanner call. Forcing one would test a separate capability and change the investigation setting for that run.

**Immediate next:** obtain a targeted live trace of unregistered tool call -> explicit ADK correction -> valid `submit_cycle_intent` accepted -> authoritative execution in the same cycle. Then run a separately scoped live exercise showing bounded/truncated output, a `retrieve_retained_evidence` call, and use of a fact obtained from that retrieval. Keep experimental scanner handoff outside these exercises.

**Return to P1.1:** run the next comparable batch from the same prepared target commit and equivalent request/model/scanner configuration, on one fixed harness code revision with Q5 unchanged. For each run, record the Experiment 1 per-run Q1–Q5 and self-evaluation fields, actual evidence/tool chronology, Intent rejection cost, implementation reassessment, deterministic validation, and task success separately from decision quality. Mark scanner non-use as non-use; do not score it as a P2.2 pass or failure. If a run invokes the experimental scanner and encounters a handoff/resource failure, investigate its cause; if a capability defect withheld decision-critical evidence, set aside the affected P1.1 inference and open targeted P2.2 acceptance.

Compare:

```text
Q2 investigation/evidence
→ Q3 ownership/control points and solution space
→ Q4 evidence-supported candidates
→ Q5 Challenge Before Commitment
→ selected solution
→ implementation/reassessment
→ deterministic validation
```

Keep task success separate from reasoning quality. Experiment 1 remains **CONTINUE** until clean repeated evidence supports a stronger disposition. The explicit return point for the optional P2.2 path is an attempted scan with a possible handoff defect, or a decision that depends on proving its live availability.
