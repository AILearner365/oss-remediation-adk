# Autonomous Agent — Work State

**Updated:** 2026-10-01. **Repository:** `AILearner365/oss-remediation-adk`, branch `context-hygiene-clone-challenge-before-commitment`. This is a development conversation bookmark, not an agent runtime checkpoint. Read [PROJECT-DIRECTION](PROJECT-DIRECTION.md) for the stages and IDs.

## Active stack and return point

1. **Main objective:** reliable, general autonomous problem solving, first evaluated on OSS remediation.
2. **S3 / P1:** engineering decision quality varies; a valid remediation can still reflect premature elimination of a better project-native control point.
3. **P1.1:** evaluate the frozen Challenge Before Commitment behavior at Q5 using the [experiment record](../EXPERIMENT_1_CHALLENGE_BEFORE_COMMITMENT.md), baseline `e92837d`.
4. **P2 support work:** remove independent harness/tool/capture contamination before judging P1.1.
5. **P2.1 — resolved for now:** explicit whole-file delete capability replaced ambiguous text-delete semantics.
6. **P2.3 - current follow-up:** `3a415f61` fixed the distinct `content`/`answer` mismatch. `022558` now exposes an unregistered ADK tool call aborting Intent capture, plus a size rejection followed by another unregistered call. Bounded tool-error recovery and size guidance are tested; live acceptance is the current boundary.
7. **P2.4 — next separate exercise:** observe truncation → retained-evidence retrieval → use of the retrieved fact in a live trace.
8. **P2.2 — separate tracked capability question:** experimental scanner runtime-resource handoff remains unobserved model-backed and is not a scanner-use requirement for P1.1.

**Current return point:** seek targeted live same-cycle recovery, then conduct the separate P2.4 live retrieval exercise and return to repeated frozen P1.1 evaluation from equivalent starting conditions. Keep P2.2 separate. Do not change Q1-Q5.

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

## Latest run outcomes

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

## Immediate next action and return to P1.1

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
