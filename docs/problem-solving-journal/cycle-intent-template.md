# Cycle {{cycle_number}} — Problem Analysis and Solution Decision

> This record captures the decision state before implementation begins. The canonical Task to Solve is supplied and rendered by deterministic orchestration; the model answers the sections below after read-only investigation.

## Model understanding

What does the model understand it has been asked to accomplish?

Explain the requested result, target scope, materially governing requirements, and complete-resolution standard. Do not propose a solution or replace, narrow, or expand the authoritative Task to Solve.

## Information, investigation and remaining uncertainty

What information was needed to develop an evidence-supported solution, and what did the model find?

| Information needed | Why it was needed | Sources examined | Finding | What remains unknown or requires execution |
|---|---|---|---|---|
| {{information}} | {{reason}} | {{actual_sources_or_methods}} | {{finding}} | {{remaining_gap}} |

### Material assumptions that remain necessary

For each assumption, state what is assumed, why it could not be established, what evidence was checked, why proceeding is reasonable, and how the selected solution controls the risk. State `None` when no material assumption remains.

When solution choice depends on how the current state is produced or controlled, investigate the existing ownership, indirection, inheritance, configuration, relationships, or management layers before selecting an intervention. Prefer the appropriate existing control point when evidence supports it rather than introducing a new override merely because one is possible.

Investigate materially different solution mechanisms reasonably suggested by repository evidence when they could materially affect requirements, constraints, compatibility, maintainability, scope, or correctness. Possibilities eliminated by evidence do not need to become candidates.

{{#if_prior_cycle}}
## Prior-cycle reassessment

Considering all prior cycles and the current repository state, what prior findings, assumptions, decisions, and implemented directions remain valid for solving the unresolved Task, and what should be reconsidered or discarded?

Cross-check all relevant accumulated history against the original Task to Solve and current evidence. Treat prior model statements as claims, not automatically established facts. Identify supported, uncertain, contradicted, incomplete, useful, discarded, and unresolved material; verify decision-critical claims where reasonably feasible; preserve uncertainty when verification is unavailable. Do not automatically continue or discard previous work.
{{/if_prior_cycle}}

## Concrete candidate solutions

What concrete solutions are supported by the available evidence?

Include only genuinely supported candidates. One candidate is valid when investigation leaves only one concrete evidence-supported solution; never manufacture alternatives merely to satisfy a count.

A candidate is not viable merely because it resolves the primary technical symptom. Reconcile every candidate against every applicable hard requirement and constraint. Do not select a candidate with an established conflict. Unresolved hard-constraint compatibility must remain explicit and prevents COMPLETE classification unless further evidence resolves it; classify it PARTIAL only when evidence supports safe constraint-compliant progress, otherwise do not present it as a candidate.

#### Candidate Solution {{identifier}} — {{specific_solution_name}}

| Question | Model answer |
|---|---|
| What exact solution is proposed? | {{answer}} |
| Why were these exact changes selected? | {{answer}} |
| What evidence supports the expected result? | {{answer}} |
| Which parts of the problem will it resolve? | {{answer}} |
| Does it satisfy every applicable requirement? | {{answer}} |
| How will it be implemented? | {{ordered_directional_sequence}} |
| How will compatibility be preserved? | {{answer}} |
| Why is the result coherent and maintainable? | {{answer}} |
| What risks or unknowns remain? | {{answer}} |
| How will the result be validated? | {{answer}} |
| Is it a COMPLETE or PARTIAL solution? | {{classification_and_justification}} |

## Selected solution

Which solution is selected, and why is it preferred?

- **Selected solution:** {{candidate_identifier_and_name}}
- **Classification:** COMPLETE or PARTIAL
- **Why it is preferred:** {{answer}}
- **Comparative coverage:** {{answer}}
- **Remaining risks:** {{answer}}
- **Evidence requiring reconsideration:** {{answer}}

Do not select a candidate with an established hard-requirement or hard-constraint conflict. Preserve unresolved hard-constraint compatibility as uncertainty and do not classify the candidate COMPLETE unless further evidence resolves it.

The selected solution is directional, not immutable. Material execution evidence may justify retaining, revising, extending, combining, or replacing it within the same cycle.
