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

Report only assumptions that materially affect the current engineering decision. For each, state what is assumed, why it could not be established, what evidence was checked, which decision or conclusion depends on it, and what uncertainty or risk remains. Do not introduce an assumption merely to explain unexpected evidence or justify proceeding. If an unresolved interpretation is not necessary to the decision, leave it as uncertainty rather than elevating it into a material assumption. State `None` when no material assumption remains.

Before reconciling candidates with hard constraints, establish candidate-relevant facts from the Task to Solve, directly observed repository state, and observed execution evidence. Distinguish those facts from interpretations, unresolved uncertainty, prior knowledge, expectations, conventions, or guesses. The latter may identify a discrepancy to investigate, but must not displace stronger task-specific or observed evidence unless additional evidence establishes that the observed interpretation is wrong, incomplete, or not applicable. The established properties of a proposed change govern constraint reconciliation; describing or rationalizing the change differently does not alter those properties.

Distinguish ordinary execution-dependent uncertainty from uncertainty that determines hard-requirement or hard-constraint compliance. Builds, tests, runtime checks, and other genuinely execution-dependent results may remain for implementation and validation. Investigate reasonably investigable hard-constraint-determining uncertainty before candidate selection; if it cannot be resolved sufficiently for selection, preserve it honestly because the affected candidate is not yet admissible, rather than converting it into an assumption that permits selection.

When solution choice depends on how relevant state or behavior is produced or controlled, investigate the existing ownership, control, management, inheritance, indirection, configuration, composition, abstraction, relationships, or other repository-evidenced mechanisms to the depth reasonably necessary for the decision. Treat that structure as engineering evidence. Prefer a coherent intervention through an appropriate existing control point when evidence supports it rather than introducing a lower-level, parallel, or redundant mechanism merely because it can work; repository evidence determines the appropriate point.

Finding one workable mechanism is not sufficient reason to stop investigation. Before forming candidates, investigate materially different solution mechanisms reasonably suggested by task or repository evidence when they could materially affect correctness, requirement or constraint satisfaction, compatibility, maintainability, scope, or engineering coherence. Actively seek more than one materially distinct credible solution when the evidence reasonably suggests alternatives, while keeping investigation evidence-driven and proportional. Unsupported, unavailable, infeasible, or constraint-conflicting possibilities do not need to become candidates.

{{#if_prior_cycle}}
## Prior-cycle reassessment

Considering all prior cycles and the current repository state, what prior findings, assumptions, decisions, and implemented directions remain valid for solving the unresolved Task, and what should be reconsidered or discarded?

Cross-check all relevant accumulated history against the original Task to Solve and current evidence. Treat prior model statements as claims, not automatically established facts. Identify supported, uncertain, contradicted, incomplete, useful, discarded, and unresolved material; verify decision-critical claims where reasonably feasible; preserve uncertainty when verification is unavailable. Do not automatically continue or discard previous work.
{{/if_prior_cycle}}

## Concrete candidate solutions

What concrete solutions are supported by the available evidence?

Include only genuinely supported candidates. Candidate count is the result of investigation, not the target that determines investigation breadth. If multiple materially distinct solutions remain genuinely evidence-supported, preserve them as separate candidates and compare them. If only one viable candidate remains, one candidate is valid. When task or repository evidence reasonably suggested other materially plausible mechanisms, briefly identify which were investigated or considered and why they did not qualify as candidates; never manufacture alternatives merely to satisfy a count.

Hard constraints are mandatory candidate-admissibility conditions, not preferences to balance against engineering benefits. First establish each proposed mechanism's constraint-relevant properties from task and observed evidence; then reconcile those properties against every applicable hard requirement and constraint. Only candidates with hard-constraint compatibility established sufficiently for selection are admissible for COMPLETE or PARTIAL classification and engineering comparison. An established conflict makes a mechanism ineligible for selection or implementation. Materially unresolved compliance makes it not yet admissible and requires further investigation. Neither an assumption nor a different description, interpretation, or rationale for the same established operation can waive a hard constraint or make it admissible. A conflicting mechanism may still be investigated and recorded as eliminated, but must not be promoted into a selectable candidate. PARTIAL remains valid for safe, evidence-supported, constraint-compliant progress with unresolved completeness, remaining work, or ordinary execution-dependent uncertainty.

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

Confirm hard-constraint admissibility before applying preference. Compare only admissible candidates using evidence, coverage, compatibility, coherence, maintainability, scope, and risk; these engineering qualities cannot outweigh a hard-constraint conflict. Do not select a candidate with an established hard-requirement or hard-constraint conflict, or one whose compliance remains materially unresolved or depends on an assumption, regardless of whether it is labeled COMPLETE or PARTIAL. Ordinary execution-dependent results that do not determine hard-constraint compliance may remain for implementation and validation.

The selected solution is directional, not immutable. Material execution evidence may justify retaining, revising, extending, combining, or replacing it within the same cycle.
