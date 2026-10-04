# Review reporting and recurring unknown-tool calls

Cloud Shell; local and remote branch `context-hygiene-clone-challenge-before-commitment` reconciled at reviewed `826089383330ba020b884699b9ba3419bf138afa`. Existing dirty historical nested repositories and untracked workspaces were preserved. Resource check before tests: about 5.2 GiB available RAM and 868 MiB free disk. Windows was not executed; Windows → Cloud Shell remains supported. Workloads were sequential.

## Deterministic review corrections

`retain_review()` previously replaced the overall outcome with the combination of semantic criterion statuses. A review of an accepted decision could therefore erase a later execution failure; the CLI also returned zero for failed semantic review. These are demonstrated development-reporting defects, not production acceptance defects.

The corrected result distinguishes:

- `capture`: original accepted-record/capture result, preserved unchanged.
- `execution`: completion of the model/session workload; a terminal failure or infrastructure blockage remains FAILED or BLOCKED even after Intent acceptance. Legacy raw results are interpreted conservatively from original outcome, terminal error, capture and accepted stop reason.
- `semanticAssessment`: combined reviewer criterion statuses, including explicit PENDING / NOT_EXERCISED.
- `outcome` / `passed`: overall scenario result. Execution gates first, then capture, then semantic assessment; only all three PASSED yields PASSED / true. `originalOutcome` retains the raw value. Pending maps to overall NOT_EXERCISED. Unexercised execution cannot be promoted by semantic review.

Review output uses exclusive file creation. Existing raw results, previous reviews, accepted exports and journals cannot be overwritten. `--output` selects a separate new evidence path. Exact accepted-journal/hash/selected-candidate binding, selected-export integrity and full criterion completeness remain required. Missing criteria reject the review; a complete review can explicitly mark a criterion PENDING with rationale/evidence. This checks integrity and reporting, not the truth of reviewer prose.

**CLI:** zero only for overall PASSED; 1 for FAILED, BLOCKED or NOT_EXERCISED/pending. Invalid/incomplete review and existing output paths also exit nonzero. F/G offline preparation now retains `offlineMechanics=PASSED` but `passed=false` / `outcome=NOT_EXERCISED`, and exits 1 because no overall scenario assessment was performed. This convention does not change other scenario families' offline checks.

[Coverage reassessment](coverage-reviewed-v2.json) remains **capture PASSED, execution PASSED, semantic FAILED, overall FAILED** because the accepted Q2 invented a retrieval provenance claim. The [actual subprocess command](coverage-review-command.json) returned 1 and records unchanged hashes of all four historical input/review artifacts. Original `acceptance-result.json`, `reviewed-result.json`, accepted export and journal in `run-20261003T191038Z-e662889c` are unchanged. No model was called for reassessment.

## Historical unknown-tool evidence

Source: `autonomous-oss-remediation-workspaces/run-20261003T191151Z-240bca87/artifacts/`. The [trace index](historical-trace-index.json) retains exact corrective messages, call names/argument keys, attempt events and initial-input digest. The original full input is `fixture/model-input.txt`, byte-identical to the first retained interaction's message (`agent/interactions/6061b81c86b04f5ea51eb14dde01f445-000001.json`). Its retained event hash was verified before use.

The first two turns end without audited text or tool calls; the audit does not establish why. Sequence 3 (turn 2) and sequence 5 (turn 3) already tell the model to use registered `submit_cycle_intent` with `cycle_number` and `answers`, and explicitly say nested answer/evidence/candidate/selection schemas are values, not callable tools.

**Earliest observable tool divergence:** turn 3, sequences **6–8** call `SubmitCycleIntentAnswers`, `SubmitCycleIntentAnswersEvidence`, and `google:python_interpreter`. Their arguments split one Intent into supposed constructors and Python code. This is observed output, not evidence of the internal cause. No legitimate `submit_cycle_intent` call precedes or follows them.

Sequences **9–11** return actual ADK callback corrections: not registered, no action executed, available tools including `submit_cycle_intent`, and shared attempts 1–3 / remaining 9–7. Sequence **13** continuation repeats the correct signature, not-callable-schema guidance and 3-used/7-left accounting. Sequences **14–16** repeat the invented names; **17–19** return attempts 4–6. Continuations **21/23** report 6-used/4-left. Turn 6 calls **24–26**, receives corrections **27–29** (attempts 7–9), then repeats calls **30–32**. The first last-batch call consumes attempt 10; the other two are blocked and recovery raises. The audit retains **nine tool responses**, not ten: the last concurrent batch aborts before a combined response event is emitted. No request after exhaustion should receive a successful recovery response. This is the existing bounded failure path, not evidence that earlier corrective feedback was absent.

The recorded input includes genuine fixture-originated successful publisher evidence and a blocked search result. Unaccepted payloads distinguish availability from unresolved compatibility, but no accepted decision exists. Unknown-tool exhaustion is **FAILED capture**, not infrastructure blockage or an accepted semantic pass.

## Actual conversion and feedback-path diagnostic

The historical audit records ADK input/events, not complete provider HTTP requests. It cannot retrospectively prove the exact historical wire body, provider-internal schema transformation, or model attention. To test the client interface rather than infer from invented names, `scripts/inspect_intent_interface.py` reuses the existing fixture, real `default_agent_session_factory`, Gemini implementation, callback and `run_until_intent`. It intercepts `google-genai`'s `async_request` **after SDK request conversion, immediately before HTTP request construction**, substitutes historical unknown-call batches, and retains only relevant declarations, callable names and feedback/continuation projections. Repeated responses/messages are stored once with per-request references; this removes duplicate payloads without losing delivery evidence. No valid Intent or corrected answer is supplied. Empty completions are explicitly scripted stand-ins for historical turns without audited output, not reconstructed hidden responses. Dummy/anonymous clients prevent credential use; neither provider is contacted.

Both Gemini API and Vertex conversion paths were inspected because historical artifacts do not establish the backend selection. Installed/pinned ADK **2.4.0**, GenAI **2.11.0**, installed Pydantic **2.13.4**; inspected source file hashes are in the trace index. Current environment is not assumed to prove historical environment values.

Retained [Gemini API request projection](provider/gemini-api.json) and [Vertex projection](provider/vertex.json) show:

- Exactly the supported phase tools. `submit_cycle_intent` is a single function declaration, requiring `cycle_number` and array `answers`.
- `parameters_json_schema` contains `$defs` named `IntentAnswer`, `EvidenceRecord`, `CandidateRecord`, `SelectionRecord`. Required answer fields are `section` and `answer`; evidence/candidates/selection are nested values, reached by local `$ref`. The invented `SubmitCycleIntentAnswers`, `SubmitCycleIntentAnswersEvidence` and `google:python_interpreter` names appear nowhere in the declaration or callable list.
- ADK `FunctionTool._get_declaration` → `build_function_declaration` produces the JSON schema; Gemini preprocessing does not lift nested types into tools. GenAI `_GenerateContentParameters_to_mldev` / `_to_vertex` preserve the declaration. The intercepted `async_request` receives the converted body; `_build_request` later removes internal top-level routing keys and attaches the body without changing nested declarations (no extra body override is configured). Both post-conversion declarations exactly match the previously retained `docs/verification/intent-shape-20261003/intent-tool-declaration.json`.
- Nine provider requests in this controlled replay retain the initial input. Requests 2/3 carry the signature/not-callable continuation before any invented call; request 4 contains the first three actual callback responses; requests 6/9 contain six/nine. Later requests carry the exact 3-used/7-left and 6-used/4-left continuations. Thus the callback responses and next-turn corrections reach the serialized request through the real ADK/session path; they are not merely printed in the harness log.
- Ten shared attempts and two blocked calls reproduce without increasing any limit. The declaration remains unchanged across the replay, and no Intent is accepted. This is **offline interface-path evidence**, not natural model recovery or a new live observation.

## Prior fixes and successful comparison

Inspected the unknown-tool callback/session recovery introduced in `1d044232`, shared checkpoint accounting in `d0bac2e9`, phase-toolset/error handling in `agent.py`, and `1c786f1d`'s no-submission continuation fix. The last already delivers exact supported signature, schema-as-data guidance and unknown-call allowance, visible in the failing trace before its first invented calls. Incoming answer-shape fixes `c0a4865a` and shared replay duplicate handling `93c30480` do not create aliases or alter tool registration. No missing continuation fix is being reimplemented.

[Comparison index](successful-traces.json): `run-20261003T191038Z-e662889c` uses the same normal Gemini 2.5 Flash agent/schema, one-cycle fixture limits and unseeded Intent path. Its sequence 10 calls the registered tool and accepts on attempt 1 in two turns. Its separate provenance failure remains FAILED, so this is successful **invocation/capture**, not proof of reasoning quality. Controlled E1/E2 `161200` / `161258` use the same tool configuration and accept a real model submission at sequence 2 after a fixture-seeded malformed attempt; they demonstrate invocation/controlled repair, not natural unknown-tool recovery. SDK versions and wire bodies were not captured in those old live traces; same-source configuration plus today's equality with the retained prior declaration is the available evidence, not an invented historical wire capture.

**Conclusion:** no demonstrated declaration, schema-conversion, feedback-loss or session defect in this interface path. Nested schema data is not registered or transmitted as extra tools. Repeated invented calls despite correct client interfaces remain observed model invocation behavior. Possible schema-to-constructor generalization, response-generation instability, provider-internal transformation or attention/salience effects remain hypotheses; names alone do not establish any one cause. Flattening schemas, renaming types, adding aliases or more instructions would be speculative here.

Production code, Q1–Q5, Challenge Before Commitment, budgets, isolation, one-agent sessions and delivery are unchanged. No paid run or unchanged trial was justified. Return to frozen P1.1 evaluation at **CONTINUE**. Accepted G reasoning remains unobserved; revisit the interface only with concrete contrary evidence, and distinguish future natural recovery from this controlled offline replay.

## Commands and verification

```bash
python -m unittest tests.unit.test_decision_review_reporting tests.unit.test_reasoning_boundary_scenarios tests.unit.test_unknown_tool_interface tests.unit.test_intent_tool_recovery tests.unit.test_evidence_boundary_acceptance -v
python -m scripts.inspect_intent_interface --output-dir ./interface-diagnostic-new
python -m scripts.reasoning_boundary_scenarios --workspace autonomous-oss-remediation-workspaces/run-20261003T191038Z-e662889c --review docs/verification/reasoning-boundaries-20261003/coverage-review.json --output ./coverage-reviewed-new.json
```

The last command should exit **1** for the retained provenance failure. Use a new output path; existing files are deliberately not replaced. The diagnostic exits zero only when its offline checks pass and never runs a paid model. Relevant test logs are retained alongside this report. These results are deterministic reporting/interface evidence, not a reasoning-quality or natural-recovery improvement claim.
