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

## Branch note

This documentation branch currently points to repository commit `5d0ee3d85363604925b4d893b98bc0d189eed519`.

The previously reviewed clean autonomous-agent baseline is `336584216733292793ea888b890e44b0c889b091`. The implementation prompt requires Codex to verify that the target implementation branch contains the autonomous-agent runtime before modifying code. It must not invent missing integration points on this documentation-only branch.
