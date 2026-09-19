# Cycle {{cycle_number}} — Intent

> This checkpoint records the best current direction before material implementation. It is provisional, permits uncertainty and reversible experiments, and does not prevent later adaptation.

## Problem as received

State the problem supplied by the user or calling system without silently rewriting its meaning. Include the requested outcome and reported symptoms, findings, or deficiencies.

## Interpreted objective

Explain the engineering outcome currently understood to be required. Clarify any difference between the literal request and the underlying objective.

## Relevant context and evidence discovered

Describe the project, system, data, environment, prior work, and observed evidence that materially affects diagnosis, strategy, constraints, risk, coverage, or validation.

Identify important evidence sources where practical. Do not describe assumptions as established facts.

## Input ambiguities, discrepancies, or missing information

Identify incomplete, inconsistent, potentially inaccurate, or open-to-interpretation information in the request, supplied data, constraints, repository state, previous conclusions, or validation evidence.

If no material ambiguity is known, state that explicitly and explain briefly why the information is currently sufficient.

## Applicable constraints and success criteria

Explain how supplied constraints apply to the current problem.

Describe the evidence needed to classify the work as:

- Fully resolved
- Partially resolved
- Blocked
- Inconclusive

Do not convert a preferred implementation technique into a constraint unless the run contract explicitly requires it.

{{#if_prior_cycle}}
## Prior-cycle learning

Explain what the previous cycle and authoritative validation supported, contradicted, or left unresolved. Identify prior assumptions that remain supported, were rejected, or still require testing.

## Relationship to the prior approach

Explain whether the current direction continues, adjusts, expands, replaces, or investigates before committing to the prior approach. A short transition label may be included, but it cannot replace the explanation.
{{/if_prior_cycle}}

## Materially credible candidate approaches

Describe only genuinely credible approaches. Do not invent alternatives to populate this section.

For each candidate, address as applicable:

### Candidate: {{candidate_name}}

- **Approach:** What would be done?
- **Expected coverage:** Which parts of the problem could it resolve?
- **Constraints:** Does it remain within supplied boundaries?
- **Advantages:** Why might it fit?
- **Risks or gaps:** What could remain unresolved or introduce risk?
- **Assumptions:** What must be true?
- **Validation:** How could it be tested?

If only one credible approach exists, explain why apparent alternatives are not viable or add no value. If final selection requires more evidence, include credible diagnostic or reversible experimental approaches.

## Selected direction

State the approach, combination, or diagnostic experiment selected for the next work phase.

## Selection rationale

Explain why the selected direction presently best fits:

- The interpreted objective
- Relevant evidence and context
- Requirement coverage
- Supplied constraints
- Compatibility and engineering risk
- Maintainability
- Ability to validate

Explain meaningful tradeoffs instead of repeating the selected direction.

## Assumptions to test

For every active material assumption, provide:

- **Assumption:** What is believed but not established?
- **Why it matters:** How could it affect the result?
- **Test:** What evidence would support or reject it?
- **Current status:** Untested, partially supported, supported, rejected, or unresolved

If there are no material assumptions, explain why existing evidence is sufficient.

## Intended work

Describe meaningful intended work. Keep it directional rather than prescribing every command or low-level step. Include reversible investigation or experimentation when applicable.

## Validation approach

Identify:

- Required checks
- Expected evidence
- Failure signals
- Evidence that should trigger adaptation
- Evidence required before readiness for independent validation

Do not describe planned validation as completed validation.

## Current uncertainties and risks

State material uncertainty or risk remaining before implementation and how execution or validation should reduce it.

## Additional decision-relevant information

Add any material observation, concern, alternative, dependency, stakeholder consideration, or contextual information not adequately represented above. Omit when unnecessary.
