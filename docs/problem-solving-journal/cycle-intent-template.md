# Cycle {{cycle_number}} — Problem Analysis and Solution Decision

> This record captures the final pre-selection decision state before authoritative implementation begins. The canonical Task to Solve is supplied and rendered by deterministic orchestration. The ordered answers are diagnostic boundaries, not a rigid reasoning waterfall; investigation may revise problem understanding, applicable engineering considerations, or the solution space before submission.

## Problem understanding in project context

What engineering problem is currently established in the context of this project?

Explain the requested result, target scope, materially governing requirements and constraints, project characteristics material to understanding the problem, material relationships among symptoms or components when supported by available evidence, and the complete-resolution standard. Do not require or assert a shared or higher-level root cause before the evidence supports one. Do not propose solutions, enumerate approaches, select mechanisms, or replace, narrow, or expand the authoritative Task to Solve.

## Information, investigation and remaining uncertainty

What decision-relevant information was needed, what investigation was actually performed, what evidence was obtained, and what remains unresolved?

| Information needed | Why it was needed | Sources examined | Finding | What remains unknown or requires execution |
|---|---|---|---|---|
| {{information}} | {{reason}} | {{actual_sources_or_methods}} | {{finding}} | {{remaining_gap}} |

Report actual investigation and evidence, not planned work. Investigate reasonably obtainable information when it could materially affect problem understanding, mechanism discovery or applicability, control structure, viability, constraints, candidate formation, or selection. When a material decision depends on information that may have changed outside the repository, obtain reasonably available current authoritative evidence and use it to discover the actual available and potentially applicable solution space, not merely to confirm a preferred solution. Prefer current primary or authoritative technical sources when reasonably available. Current external evidence may establish what options and documented properties currently exist; repository and execution evidence establish what applies to and happens in this project. Failed, blocked, incomplete, or inconclusive research is not evidence that an option does not exist.

### Material assumptions that remain necessary

Report only assumptions that materially affect the current engineering decision. For each, state what is assumed, why it could not be established, what evidence was checked, which decision or conclusion depends on it, and what uncertainty or risk remains. An assumption must not substitute for reasonably obtainable repository evidence or override stronger task, repository, or execution evidence. State `None` when no material assumption remains.

Distinguish ordinary execution-dependent uncertainty from uncertainty that determines hard-requirement or hard-constraint compliance. Ordinary build, test, runtime, and authoritative-validation outcomes may remain for implementation and validation. Investigate reasonably investigable hard-constraint-determining uncertainty before selection; if it remains unresolved, do not convert it into an assumption that permits selection.

When solution choice materially depends on how relevant state or behavior is produced or controlled, investigate the existing ownership, control, management, inheritance, indirection, configuration, composition, abstraction, relationships, or other repository-evidenced mechanisms. Record the evidence about those boundaries here; the engineering conclusion derived from it belongs in the synthesis section. When candidate viability depends on a repository-specific premise that isolated investigation can reasonably test, obtain sufficient evidence before treating the premise as established. This requires decision-sufficient support, not exhaustive proof, testing every candidate, or proving final success.

{{#if_prior_cycle}}
## Prior-cycle reassessment

Considering all prior cycles and the current repository state, what prior findings, assumptions, decisions, and implemented directions remain valid for solving the unresolved Task, and what should be reconsidered or discarded?

Treat prior model statements as claims. Cross-check them against current repository state, objective command evidence, deterministic validation, and other permitted authoritative sources. Preserve useful work and unresolved uncertainty; do not automatically continue or discard a prior direction.
{{/if_prior_cycle}}

## Project-applicable engineering synthesis and high-level solution space

Given the established problem, constraints, evidence, and remaining uncertainty, what engineering synthesis applies to this project, and what high-level solution space follows?

Identify only the engineering principles, established practices, ownership or control boundaries, architectural relationships, support or compatibility boundaries, and other considerations that materially shape this decision. Explain why their rationale matters to this project rather than invoking generic `best practice`. Determine whether each material consideration applies as-is, requires adaptation, should be rejected here, or remains uncertain.

Derive the materially distinct high-level solution approaches supported by that synthesis. Separate viability from preference. Do not eliminate an approach merely because another appears preferable. Record evidence-based elimination or unresolved viability when material. The newest option is not automatically correct. One approach is valid when evidence eliminates the others; there is no minimum approach count and alternatives must not be manufactured.

Keep the synthesis proportional. Do not repeat the evidence log, enumerate generic practices, exhaustively catalog theoretical solutions, specify exact edits, provide an implementation plan or candidate-level validation, compare concrete candidates, select a solution, or expose private chain-of-thought.

## Concrete candidate solutions

What concrete solutions translate the surviving high-level approaches into specific implementable changes?

Form candidates only from investigation actually performed, evidence actually obtained, and the project-applicable synthesis. Candidate count is an outcome of investigation and synthesis. Preserve materially distinct viable approaches as separate candidates when appropriate; one candidate remains valid when evidence eliminates the others. Never manufacture alternatives.

Hard constraints are mandatory admissibility conditions. Establish each candidate's constraint-relevant properties from task and observed evidence, then reconcile them against every applicable hard requirement and constraint. Do not select a candidate with an established conflict or materially unresolved hard-constraint compliance. PARTIAL remains available only for safe, evidence-supported, constraint-compliant progress.

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

Confirm hard-constraint admissibility before applying preference. Compare surviving admissible candidates using evidence, coverage, compatibility, coherence, maintainability, scope, and risk. Preference cannot outweigh a hard-constraint conflict or retroactively make a viable alternative non-viable.

The selected solution is directional, not immutable. Material execution evidence may justify retaining, revising, extending, combining, or replacing it within the same cycle.
