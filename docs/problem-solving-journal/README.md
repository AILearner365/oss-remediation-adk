# Problem-Solving Decision Journal

This folder defines a technology-neutral journal protocol for autonomous problem solving.

The protocol requires two model-authored checkpoints per work cycle:

1. **Problem Analysis and Solution Decision** — the model's evidence-grounded understanding, investigation, candidates, and selected solution before material work.
2. **Cycle Outcome** — what actually happened after execution and self-validation.

Deterministic code appends:

3. **Deterministic Validation** — authoritative checks and contradictions.
4. **Final Resolution** — the terminal run result, coverage, limitations, and delivery state.

## Design principles

- Constrain reporting and lifecycle timing, not the engineering solution.
- Permit uncertainty, reversible experiments, additional sections, and strategy changes.
- Do not require artificial alternatives.
- Keep the journal append-only; later evidence must not rewrite earlier intent.
- Use Markdown as the human-readable decision artifact.
- Let deterministic code own headings, ordering, capture verification, and append operations.
- Keep machine events and hashes as internal audit metadata.
- Distinguish structural completeness from semantic accuracy.
- Accept compact typed decision records; render readable Markdown in deterministic code.
- Keep deterministic validation authoritative.
- Preserve safe partial progress without presenting it as full resolution.

## Runtime lifecycle

1. Read-only discovery.
2. Submit and validate Problem Analysis and Solution Decision.
3. Enable implementation capabilities.
4. Execute and self-validate.
5. Disable mutation capabilities.
6. Submit and validate Cycle Outcome.
7. Run deterministic validation.
8. Continue to another cycle or finish.
9. Apply explicit full, partial, blocked, inconclusive, and no-change delivery rules.

## Files

- [cycle-intent-template.md](cycle-intent-template.md)
- [cycle-outcome-template.md](cycle-outcome-template.md)
- [deterministic-validation-template.md](deterministic-validation-template.md)
- [final-resolution-template.md](final-resolution-template.md)
- [CODEX_IMPLEMENTATION_PROMPT.md](CODEX_IMPLEMENTATION_PROMPT.md)

## Current checkpoint API

`submit_cycle_intent(cycle_number, answers)` takes ordered section objects with `section` and substantive `answer`. The investigation object also has `evidence` records (`question`, `source`, `finding`, `uncertainty`). The candidate object has `candidates` records (`id`, `name`, `solution`, `evidence`, `constraints`, `validation`, `classification`). The selection object has `selection` (`candidate_id`, `rationale`, `challenge`). Classification is `COMPLETE` or `PARTIAL`. These fields carry decision facts; the prose carries material explanation and uncertainty. Q1–Q5 investigation, evidence, constraint, and challenge requirements remain in the runtime questionnaire.

Rejected Intent does not append to the journal or open authoritative execution. Valid section objects remain in a cycle-scoped unaccepted draft; a retry may submit only corrected sections. The draft is cleared on acceptance, capture failure, or cycle transition. `submit_cycle_outcome` requires the implementation result and material Intent-versus-implementation reassessment. Observable chronology is rendered from events. The model supplies rationale and self-validation; the harness does not infer them from actions.

Before requesting Outcome, the harness captures the current authoritative baseline-to-working-tree diff, changed paths, and timestamped command/scan observations separated by workspace. The prompt contains a bounded diff (12,000 characters), bounded check observations, completeness flags, and content-bound references to the full snapshot, diff, and observations. Outcome permits `retrieve_retained_evidence` for these already-authorized artifacts; repository reads, shell, edits, and scans remain disabled. The accepted journal and delivery summary include the observed evidence separately from model-authored explanation. Replacement-session evidence indexes also retain these references. A demonstrable `NO_CHANGE_REQUIRED` status versus a successfully captured nonempty change set is rejected with the diff reference, using the existing allowance. Arbitrary prose is not validated by string matching: a stale explanation can still be accepted, so acceptance is not a factual-correctness guarantee. The snapshot remains available to audit or correct that explanation. Later independent validation remains authoritative for its own checks.

Each checkpoint has its own ten-attempt allowance per cycle. An unknown or unavailable ADK tool invocation in that phase and every `submit_cycle_intent` or `submit_cycle_outcome` call each consume one attempt, in either order. A valid submission may be accepted on attempt ten; an invalid submission or unknown invocation on attempt ten returns `retryAllowed: false`, and later submissions cannot be accepted in that checkpoint. The accepted submission consumes an attempt but is not a rejection. Attempts and blocked post-limit calls are recorded in the trace. Execution-phase unknown invocations have a separate bounded recovery allowance. Event-rendered Outcome action lines carry `workspaceKind` when observed, so experimental edits and builds remain distinguishable from authoritative work.

This is a schema migration for new submissions. Historical Markdown journals and saved traces remain readable as recorded; they are not rewritten or treated as current API examples. Phase exposure uses ADK's toolset interface, while server-side phase checks remain authoritative. Unknown or unavailable invocations receive bounded same-session feedback where ADK preserves the protocol. Source evidence references remain authorized within the run and are included in concise continuation context after a failed checkpoint; when there are many, a retrievable manifest preserves the older references. Research retains raw response bytes and extracted text separately, with explicit acquisition, extraction, source truncation, and display-bounding states.
