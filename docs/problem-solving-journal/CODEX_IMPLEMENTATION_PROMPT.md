# Codex Implementation Prompt — Markdown Problem-Solving Journal

Implement the generic Markdown problem-solving journal described in this folder.

## Repository and branch context

- Repository: `AILearner365/oss-remediation-adk`
- Target branch: `decision-markdown-clone-update-strategy-clone-xray-improve-4`
- Documentation folder: `docs/problem-solving-journal/`
- Previously reviewed clean autonomous-agent baseline: `336584216733292793ea888b890e44b0c889b091`
- Decision-state proof branch: `decision-state-clone-update-strategy-xray-improve-4`

The proof branch and its workspaces are evaluation evidence only. Do not merge or copy its generated workspaces, cloned repositories, logs, caches, dependency-tree files, scanner outputs, credentials, delivery artifacts, or temporary files into the implementation.

## Mandatory baseline check

Before changing runtime code:

1. Inspect the exact target branch and repository history.
2. Verify that the target contains the autonomous runtime, including the orchestrator, prompt construction, developer capabilities, workspace trace storage, deterministic validation, delivery handling, agent cycle artifacts, and tests.
3. Compare it with the supplied implementation reference.
4. Report the exact target HEAD and reference SHA.

If the autonomous runtime is absent from the target branch, stop before implementation and report `IMPLEMENTATION_BASELINE_MISSING`. Do not reconstruct hundreds of commits, copy an entire implementation from another branch, or invent integration points. Ask for the target branch to be recreated or fast-forwarded from an approved clean implementation reference.

Do not treat the proof branch as an implementation base unless explicitly authorized.

## Objective

Replace prompt-dependent, model-voluntary decision recording with an orchestrator-managed, Markdown-first problem-solving journal.

Every remediation cycle must produce:

1. A model-authored Cycle Intent before material repository mutation.
2. A model-authored Cycle Outcome after execution and self-validation.
3. A system-authored Deterministic Validation section.
4. A system-authored Final Resolution section when the run terminates.

The journal must make the problem-solving path visible without prescribing the technical solution.

## Governing principles

- Constrain reporting completeness and lifecycle timing, not engineering direction.
- Permit uncertainty, reversible experiments, additional sections, and strategy changes.
- Do not require artificial alternatives.
- Do not require the agent to follow an invalidated initial plan.
- Do not require a record for routine navigation, searches, command selection, or low-level edits.
- Keep deterministic validation authoritative.
- Preserve safe partial progress without presenting it as full resolution.
- Do not request or expose hidden chain-of-thought. Capture concise, externally useful engineering state, evidence, rationale, assumptions, and conclusions.
- Do not make the caller update the existing input payload.
- Keep the design technology-neutral. OSS remediation guidance may be layered on top but must not define the generic journal lifecycle.

## Canonical templates

Use these files as the normative content contracts:

- `docs/problem-solving-journal/cycle-intent-template.md`
- `docs/problem-solving-journal/cycle-outcome-template.md`
- `docs/problem-solving-journal/deterministic-validation-template.md`
- `docs/problem-solving-journal/final-resolution-template.md`

Do not silently remove questionnaire topics. Minor wording changes are acceptable only when needed for runtime rendering or unambiguous validation.

## Journal artifact

Create one append-only run artifact:

`agent/decision-journal.md`

Its logical structure is:

- Run Contract
- Cycle 1 Intent
- Cycle 1 Outcome
- Cycle 1 Deterministic Validation
- Cycle 2 Intent
- Cycle 2 Outcome
- Cycle 2 Deterministic Validation
- Additional cycles as required
- Final Resolution

Earlier accepted sections must never be overwritten by later model output. Corrections and contradictions are appended to later sections.

## Model and system ownership

The model owns narrative answers:

- Problem interpretation
- Relevant context
- Ambiguities
- Candidate approaches
- Selected direction
- Selection rationale
- Assumptions
- Intended work
- Actual work
- Deviations
- Evidence interpretation
- Remaining uncertainty
- Cycle conclusion

Deterministic code owns:

- Journal path
- Run and cycle identifiers
- Heading names and order
- Checkpoint ordering
- Capture timestamps and hashes
- Append-only writing
- Required-section verification
- Lifecycle status
- Deterministic validation content
- Capture-verification indicators
- Delivery eligibility
- Final outcome projection

The model must not directly edit `decision-journal.md`.

## Submission design

Provide dedicated metadata-only submission capabilities for:

- Cycle Intent
- Cycle Outcome
- Optional material note, if it can be added without complicating the first implementation

The model may supply Markdown paragraphs, lists, inline code, and optional subsections in answer content. Deterministic code must render canonical top-level and required section headings.

Internal tool-call transport may be structured. The persisted human-facing decision content must be Markdown.

Do not parse arbitrary conversational output to recover a checkpoint.

## Structural validation

Validate submissions before appending them.

At minimum, deterministically verify:

- Correct active cycle and checkpoint type
- Every required section has an answer
- No duplicate required section
- No placeholder-only answer such as `TBD`, `TODO`, or unexplained `N/A`
- Allowed lifecycle status
- Per-section and total size limits
- Checkpoint has not already been accepted
- Intent precedes material mutation
- Outcome follows execution
- Additional sections are allowed
- Prior journal content is unchanged
- Rendered Markdown parses successfully
- Accepted content hash matches appended content

Use a Markdown/CommonMark parser or deterministic renderer. Do not use HTML validation or a single permissive regular expression as the primary validator.

A rejected checkpoint must:

- Return precise missing or invalid section feedback
- Emit a technical rejection event
- Leave the canonical journal unchanged
- Permit a bounded retry
- Avoid consuming operational repository tool calls

After retry exhaustion, preserve existing work, mark capture incomplete, and require manual review rather than fabricating a checkpoint.

## Lifecycle enforcement

Implement explicit orchestrator phases equivalent to:

1. `DISCOVERY`
2. `INTENT_REQUIRED`
3. `EXECUTION`
4. `OUTCOME_REQUIRED`
5. `DETERMINISTIC_VALIDATION`
6. `DELIVERY_OR_CONTINUATION`

### Discovery

Allow repository and system discovery sufficient to form an intent.

Material repository mutation must not occur before accepted intent. Because the current unrestricted shell can mutate files, merely disabling the text-edit tool is insufficient.

Use phase-specific capabilities or another enforceable boundary. Also compare repository state before and after discovery as defense in depth. If material mutation occurred before intent, mark capture late and do not falsely classify it as complete.

Permit a Cycle Intent to select a reversible diagnostic experiment when evidence is insufficient for a final remediation choice.

### Execution

After accepted intent, enable normal implementation and self-validation capabilities.

The agent remains free to adapt. Do not require it to pause for forms after every command or minor change.

### Outcome

After execution ends for any reason, remove mutation and shell capabilities and invoke a bounded metadata-only outcome turn.

Provide:

- Accepted Cycle Intent
- Relevant execution events
- Repository diff/change summary
- Command, build, test, and scan evidence
- Errors and rejected operations
- Remaining budget/time context

Require Cycle Outcome for successful, partial, blocked, failed, inconclusive, and no-change cycles.

### Deterministic validation

Run only after the Outcome checkpoint succeeds or bounded capture recovery is exhausted.

Append the system-generated validation section. Preserve both confirmed and contradicted model claims.

If validation fails and another cycle is available, the next Cycle Intent receives:

- Original run contract
- Prior intents and outcomes
- Authoritative validation learning
- Current repository state
- Remaining unresolved requirements

Do not rely on the legacy summary as the authoritative continuation state.

## Compatibility with summary and WORKING_STATE

Retain the existing raw agent summary in `agent/cycle-N.json` initially for compatibility and debugging.

During migration:

- The journal is the authoritative cross-cycle problem-solving state.
- Do not let an unstructured summary override the journal.
- Retain legacy `WORKING_STATE` only if required by existing compatibility tests.
- Do not inject both journal state and a contradictory truncated WORKING_STATE into continuation prompts.
- Clearly mark any deprecated compatibility field.
- Do not remove legacy fields in the same change unless tests and consumers prove it safe.

Cycle artifacts should reference or include capture metadata for the accepted journal sections without duplicating the entire journal unnecessarily.

## Capture status

Expose capture quality separately from remediation and validation outcomes.

Support at least:

- `COMPLETE`
- `LATE`
- `INCOMPLETE`
- `MISSING`

A complete cycle requires an accepted Intent before material mutation and an accepted Outcome after execution.

Capture status must never convert deterministic validation failure into success or success into failure.

## Evidence grounding

Where existing events provide stable identifiers, permit journal answers to reference:

- Command evidence
- File observations
- Build/test results
- Scan results
- Validation checks
- Diff artifacts

Deterministically verify referenced identifiers exist when feasible.

Do not claim semantic correctness solely because a section is nonempty.

## Partial remediation and delivery

Separate:

- Remediation outcome
- Deterministic validation status
- Capture status
- Delivery eligibility

Support at least these remediation outcomes:

- `FULLY_VALIDATED`
- `PARTIALLY_REMEDIATED`
- `BLOCKED`
- `FAILED`
- `INCONCLUSIVE`
- `NO_CHANGE_REQUIRED`

A partial draft delivery may be eligible only when deterministic evidence establishes that:

- Preserved changes are internally consistent and independently useful
- Required build/tests pass
- Supplied constraints remain satisfied
- No new prohibited finding or regression is introduced
- Remaining findings or requirements are explicitly disclosed
- The delivery is clearly marked for manual review

Do not create an empty PR for a no-change outcome.

Do not deliver when the repository is broken, changes are unsafe, validation cannot establish safety, or the only effect is suppression/concealment.

If existing delivery contracts do not safely support partial delivery, implement the outcome and eligibility model but default partial delivery to manual review. Do not weaken existing full-success gates merely to produce a PR.

## Diagnostic and investigation artifacts

Prevent files created only for investigation from entering delivery.

The real-run proof showed `dependency_tree.txt` files being committed accidentally.

Implement general protection:

- Prefer command artifacts outside the repository or ignored build locations
- Include final diff hygiene in the Outcome evidence
- Detect newly introduced likely diagnostic artifacts conservatively
- Warn and require cleanup or manual review
- Do not delete legitimate project files based only on a broad filename pattern
- Test the observed dependency-tree case without making the design repository-specific

## Internal audit events

Retain small machine-readable events for operational auditing, for example:

- Intent submission accepted/rejected
- Outcome submission accepted/rejected
- Journal section appended
- Capture classified
- Deterministic validation appended
- Delivery eligibility determined
- Run finished

Events may contain checkpoint metadata, hashes, paths, cycle numbers, status, and failure codes. Avoid duplicating the entire Markdown narrative into every event.

Restart/resume reconstruction may be deferred if not already supported, but document the limitation accurately.

## Tests

Add focused unit and integration coverage for:

1. Complete Cycle Intent accepted before mutation.
2. Missing, empty, duplicate, placeholder, oversized, and malformed sections rejected.
3. Additional model-defined subsections accepted.
4. A single credible approach accepted without invented alternatives.
5. A diagnostic experiment accepted as provisional intent.
6. Mutation capabilities unavailable before accepted intent.
7. Unrestricted shell cannot bypass the pre-intent mutation boundary.
8. Repository-state change before intent classified late.
9. Execution capabilities enabled only after intent.
10. Outcome requested after successful, partial, blocked, failed, inconclusive, and no-change execution.
11. Mutation and shell unavailable during Outcome.
12. Outcome records intended-versus-actual and unresolved coverage.
13. Earlier journal sections remain immutable.
14. Deterministic validation appended by code, not model.
15. Contradictions preserved and visible.
16. Failed validation feeds the next cycle without replacing the original objective.
17. Cycle 2 Intent includes prior-cycle learning.
18. Capture status remains separate from validation status.
19. Full deterministic success plus complete capture retains normal delivery.
20. Deficient capture requires manual review without discarding validated work.
21. Safe partial remediation is represented without being called full success.
22. Unsafe or broken partial changes are not deliverable.
23. No-change outcome does not create an empty PR.
24. Diagnostic artifacts are detected or excluded.
25. Raw cycle summary compatibility remains intact.
26. Journal context remains bounded for model input.
27. Existing deadlines and operational budgets remain enforced.
28. Existing scanner, constraint, validation, and delivery authority remains intact.

Use scripted agent sessions for deterministic integration tests. Add a small number of real-model evaluations only after deterministic coverage is stable.

## Validation

Run:

- New journal unit tests
- Prompt and capability-policy tests
- Autonomous orchestrator integration tests
- Complete autonomous unit and integration suites
- Compilation
- Whitespace/diff checks
- Full repository discovery

Compare failures against the exact approved implementation base. Distinguish pre-existing failures from branch-specific regressions.

Review the final diff for:

- Generated workspaces
- Cloned repositories
- Logs
- Dependency trees
- Scanner outputs
- Credentials or tokens
- Temporary caches
- Unrelated source changes

## Deliverable report

Report:

- Exact base and target commits
- Architecture and lifecycle implemented
- Files changed
- Journal artifact format
- How required sections are validated
- How mutation gating is enforced
- How cycle continuation works
- How partial remediation and delivery are represented
- Compatibility behavior for summary and WORKING_STATE
- Tests and exact results
- Base comparison
- Remaining limitations

Do not commit, push, open a PR, or modify external delivery resources unless explicitly requested.
