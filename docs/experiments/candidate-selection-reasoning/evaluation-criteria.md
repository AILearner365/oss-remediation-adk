# Reasoning-quality evaluation

Evaluation compares observable behavior with sealed expectations and independent
validation. Final build success is one evidence item, not the score itself.

## Required dimensions

Each dimension is reported with concrete evidence IDs as `SUPPORTED`,
`PARTIAL`, `UNSUPPORTED`, or `NOT_OBSERVABLE`; no aggregate numeric score is
required.

1. **Goal and constraint fidelity:** proposed changes remain in scope and honor
   version, compatibility, change-budget, and validation constraints.
2. **Fact/uncertainty discipline:** factual claims cite acquired evidence;
   unknowns, source failures, incomplete advisories and untested compatibility
   remain explicit.
3. **Candidate discovery breadth:** credible strategy classes are discovered
   from project/source evidence; material alternatives are neither omitted nor
   rejected without investigation. Quantity alone earns no credit.
4. **Mechanism correctness:** reasoning distinguishes Boot management,
   application control, direct/transitive selection, path absence, advisory
   applicability, and compatibility.
5. **Comparison quality:** original addressed/still/unknown findings, new
   findings, graph churn, control provenance and regression risks are compared
   without count-only or newest-is-best shortcuts.
6. **Selection justification:** preference follows the stated goal and evidence,
   identifies assumptions requiring validation, and does not overclaim safety.
7. **Validation response:** contradictory evidence invalidates the relevant
   assumption; revision materially changes the plan or explicitly abstains.
8. **Traceability and calibration:** an evaluator can reconstruct why candidates
   appeared, changed, were rejected, and were selected; confidence matches
   evidence completeness.

## Explicit defect taxonomy

Record each occurrence with severity and evidence:

- premature commitment before inspecting effective resolution;
- missed credible alternative;
- unsupported fixed version or advisory alias merge;
- query absence treated as proof of safety;
- managed version treated as effective application version;
- path absence generalized beyond the examined path;
- new finding or residual finding omitted;
- compatibility inferred from vulnerability remediation;
- validation failure ignored, explained away, or repeated unchanged;
- source/tool failure misclassified as approach failure;
- strategy changed without connecting new evidence to the revision;
- excessive exploration that does not reduce a relevant uncertainty.

## Comparison with expectations

The sealed evaluator checks required discoveries, prohibited claims, acceptable
strategy envelopes, mandatory validation facts, and revision obligations. A
different final strategy may still be credible if its evidence satisfies the
goal and constraints. Conversely, matching an expected strategy fails the
reasoning evaluation if the trace used unjustified claims or missed decisive
contradictory evidence.

Report separately: decision quality, final candidate validation, evidence
coverage, and operational reliability. Do not collapse them into “success.”
