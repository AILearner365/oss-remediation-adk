# Cycle {{cycle_number}} — Outcome

> This checkpoint records what actually happened after execution and self-validation. It must be completed for successful, partial, blocked, failed, and inconclusive cycles.

## Cycle outcome status

Select one:

- `READY_FOR_INDEPENDENT_VALIDATION`
- `PARTIALLY_REMEDIATED`
- `BLOCKED`
- `FAILED`
- `INCONCLUSIVE`
- `NO_CHANGE_REQUIRED`

Explain why the status fits the evidence. Readiness is not final success; deterministic validation remains authoritative.

## Work actually performed

Describe material changes, investigations, experiments, corrective actions, and relevant reverted or abandoned work. Avoid a command-by-command transcript unless a command materially affected the outcome.

## Evidence actually observed

List successful, failed, incomplete, and inconclusive checks; tooling or environmental errors; and material repository or system observations.

Separate observed evidence from conclusions. Reference command, file, scan, validation, or artifact identifiers where available.

## Intended versus actual

Compare the accepted Cycle Intent with what happened:

- Which intended work was completed?
- Which intended work was not completed?
- What additional work was introduced?
- Did the original direction remain suitable?
- Did the final implementation materially differ?

If no material deviation occurred, state that explicitly.

## Material deviations and their causes

For each material deviation, explain what changed, what evidence caused it, why adapting was preferable, and how it affected coverage, constraints, risk, maintainability, or validation.

Do not treat routine navigation or minor implementation details as strategy deviations.

## Approaches attempted, rejected, or abandoned

For every material approach not retained, explain what was attempted, why it was inadequate or unnecessary, the supporting evidence, the failure category, and whether useful progress was preserved.

If no material approach was rejected or abandoned, state that explicitly.

## Final approach present at cycle end

Describe the approach actually represented by the repository or system state. Do not include planned but unapplied work.

## Assumption results

For each original or newly discovered material assumption, provide:

- **Assumption**
- **Final status:** Supported, rejected, partially supported, or unresolved
- **Evidence**
- **Effect on implementation or conclusion**

## Requirement and problem coverage

### Satisfied

List portions supported by observed evidence.

### Conditional

List portions that appear satisfied but depend on incomplete, unreliable, or external verification.

### Unresolved

List everything still unresolved.

### Not applicable

Identify supplied requirements determined not to apply, with justification.

## Constraints and regression assessment

Explain constraint compliance, compatibility implications, new risks, failures or findings, unrelated changes, and investigation-only artifacts that must not be delivered.

## Self-validation assessment

For each important activity, distinguish:

- Planned but not run
- Run and passed
- Run and failed
- Run but inconclusive
- Prevented by an environmental or tooling blocker

Explain what independent validation must still confirm.

## Remaining work, blockers, or uncertainty

For each remaining item, state why it remains, whether another cycle can resolve it, whether a constraint prevents resolution, whether external input is needed, and whether safe partial delivery has independent value.

## Partial-remediation value

When partial:

- What independently useful improvement was completed?
- Which findings or requirements remain?
- Are preserved changes internally consistent and safe?
- Do build and tests remain healthy?
- Was any prohibited issue introduced?
- Would a draft manual-review delivery provide value?
- What must be prominently disclosed?

If not partial, state that this section is not applicable.

## Cycle conclusion

Concise summary of what was intended, what happened, why meaningful deviations occurred, what evidence currently establishes, what remains unresolved, and the recommended next step.

## Additional decision-relevant information

Add material information not adequately represented above. Omit when unnecessary.
