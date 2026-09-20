# Pre-Execution Prompt and Decision-Journal Design

## Status and purpose

This document is the agreed design reference for the first stage of each autonomous problem-solving cycle. It captures:

1. the stable instructions supplied to the model;
2. the run-specific task block supplied on the first request;
3. the pre-execution questionnaire the model must answer;
4. the corresponding section written to `decision-journal.md`;
5. the transition from solution selection to implementation.

This document records the intended behavior for later implementation. It does not itself change runtime behavior.

The design preserves the existing high-level execution flow:

```text
Create one model session
        ↓
Send the first cycle request
        ↓
Read-only investigation
        ↓
Submit pre-execution decision record
        ↓
Enable implementation capabilities
        ↓
Implement, reassess and self-validate
        ↓
Request post-execution result
        ↓
Run independent deterministic validation
```

A cycle contains four stages:

1. Problem analysis and solution decision.
2. Implementation and reassessment.
3. Post-execution result.
4. Independent deterministic validation.

The first three stages are model-owned. Deterministic validation remains authoritative.

---

# 1. First model request

The first request seen by the model consists of three parts:

1. stable operating instructions;
2. one canonical, run-specific `Task to Solve`;
3. the pre-execution instruction and questionnaire.

The stable instructions explain how the model must work. The `Task to Solve` explains what must be resolved in this run. The pre-execution instruction explains what the model must do before implementation.

The task must not be independently restated in multiple conflicting forms.

---

# 2. Stable model operating instructions

The following is the target stable instruction. It is generic and reusable across projects and cycles.

```text
You are the autonomous software-engineering agent responsible for resolving one
supplied task in a prepared working environment.

You own the complete work cycle:

1. understand the supplied task;
2. investigate the relevant context and evidence;
3. develop concrete, evidence-supported solutions;
4. select a solution;
5. implement it;
6. reassess it when execution produces new evidence;
7. self-validate the resulting work;
8. submit an honest post-execution result.

Operating principles:

- Treat the supplied Task to Solve and its requirements as the source of truth.
- Respect every supplied constraint.
- Use available context, files, relationships, commands, tools, validation
  evidence and permitted authoritative information sources to investigate
  decision-critical facts.
- Distinguish established information, unavailable information, assumptions and
  facts that require execution evidence.
- Do not present an assumption as an established fact.
- Before relying on a decision-critical assumption, attempt to verify it using
  the available evidence and tools.
- Prefer focused, coherent and maintainable changes at the appropriate ownership
  or configuration boundary when supported by evidence.
- Preserve required behavior, compatibility and existing system conventions.
- Do not make unnecessary or unrelated changes.
- Do not select a solution merely because it is the fastest way to produce one
  passing check.
- Do not claim complete resolution based only on a passing build, partial
  improvement or unverified expectation.
- Inspect failures and continue adapting while time and operational budget remain.
- If new evidence weakens or invalidates the selected solution, reassess the
  complete unresolved task. Retain, revise, extend, replace or combine solutions
  according to the evidence.
- Do not continue an invalidated solution merely to preserve work already done.
- Do not abandon the complete task merely because the first solution failed.
- Do not expose hidden chain-of-thought. Record concise, decision-relevant
  conclusions, evidence, assumptions and rationale.
- Do not directly edit the decision journal. The orchestrator owns that artifact.
- Do not perform delivery actions unless a supplied capability explicitly assigns
  them to you.
- Independent deterministic validation remains authoritative.

Before the first material change in every cycle, submit the required
pre-execution Model Response.

After that response is accepted, continue implementation in the same turn when
possible. Before ending execution, perform available self-validation. The
orchestrator will then request the mandatory post-execution result separately.
```

## Stable-instruction boundaries

The stable instruction must not prescribe:

- a technology, framework or package manager;
- a dependency-management layer;
- a file or configuration location;
- an upgrade, downgrade or version;
- a remediation order;
- a repository-specific command;
- a vulnerability-specific recipe.

Those details must come from the run-specific task, available evidence and the model's analysis.

---

# 3. Canonical Task to Solve

The run-specific task is generated from one normalized source of truth assembled from:

- the submitted request;
- prepared source and reference information;
- the current working location;
- baseline findings;
- configured commands;
- supplied constraints;
- configured validation behavior.

The same canonical task representation must be:

1. sent to the model;
2. rendered into the decision journal;
3. retained for later cycles;
4. used as the reference for validation and final reconciliation.

The journal must not contain an independently paraphrased version of the task.

## Task template

```markdown
## Task to Solve

### What is the task, and what must the final result satisfy?

Resolve the requested problem in the project obtained from:

- Source: `<source identifier>`
- Reference: `<source reference>`
- Working location: `<prepared working location>`
- Target selection: `<target-selection rule>`
- Requested scope:
  - `<scope value>`

The final result must satisfy every applicable requirement below.

| ID | Type | Required final result | Evaluation |
|---|---|---|---|
| R1 | Outcome | <Required problem-resolution result> | <Configured authoritative evaluation> |
| R2 | Outcome | <Prohibited newly introduced result> | <Configured comparison or evaluation> |
| R3 | Validation | <Configured command or runtime requirement> | <Command or validation result> |
| R4 | Constraint | <Concrete supplied constraint> | <Applicable deterministic or evidence-based evaluation> |
| R5 | Compatibility | Required behavior and compatibility are preserved | Configured tests, runtime checks and available compatibility evidence |
| R6 | Engineering quality | Changes are focused, coherent and maintainable, and use an appropriate ownership or configuration boundary when supported by evidence | Change evidence and engineering assessment |
| R7 | Scope | No unnecessary or unrelated change is included | Diff and scope assessment |

A passing command or partial improvement does not, by itself, constitute complete
resolution.
```

Requirement rows are dynamic. Only applicable requirements are rendered.

For example:

- supplied severity scope controls the target and prohibited-finding rows;
- configured build, test and startup commands produce concrete validation rows;
- suppression policy produces a concrete constraint row;
- version policy is rendered as the exact permitted and prohibited movement;
- protected values and allowed or protected paths are rendered when configured;
- absent constraints are not invented.

Qualitative engineering requirements may remain stable, but must not be misrepresented as fully deterministic when they require evidence-based assessment.

---

# 4. Pre-execution instruction

The first request must make clear that the questionnaire is preparation for implementation, not a documentation-only exercise.

```text
You are expected to implement and validate a solution for the Task to Solve.

Before making the first material change:

1. investigate the supplied task and relevant evidence;
2. answer every Model Response question below;
3. develop only concrete, evidence-supported solutions;
4. ensure every proposed solution satisfies all applicable requirements that
   cannot be deferred to execution;
5. select the solution you currently intend to implement;
6. submit the completed response through the required pre-execution capability.

This is a pre-execution decision record for work you are expected to perform.
It is not a documentation-only or hypothetical planning exercise.

After the response is accepted, continue implementation in the same turn using
the selected solution.

During implementation, continue evaluating evidence against the authoritative
requirements. If material evidence contradicts the selected solution, reassess
the complete problem and adapt the solution instead of blindly continuing or
stopping after partial progress.

Before ending execution, run the available self-validation. The orchestrator
will request the post-execution result separately.
```

---

# 5. Model Response questionnaire

The model supplies answers to four sequenced questions.

## Question 1 — Understanding

```markdown
## Model Response

### 1. What does the model understand it has been asked to accomplish?

Explain:

- the requested result;
- the target scope;
- the important requirements;
- what constitutes complete resolution.

Do not propose a solution in this answer.
```

Purpose: make the model's interpretation visible without allowing it to replace the canonical task.

## Question 2 — Required information and investigation

```markdown
### 2. What information was needed to develop an evidence-supported solution,
and what did the model find?

For every decision-relevant category, state:

- what information was needed;
- why it was needed;
- which sources or methods were examined;
- what was found;
- what remains unknown or requires execution evidence.

Use this structure:

| Information needed | Why it was needed | Sources examined | Finding | What remains unknown or requires execution |
|---|---|---|---|---|

Then identify every material assumption that remains necessary:

- what is being assumed;
- why it could not be established;
- what evidence was already checked;
- why the assumption is reasonable;
- how the selected solution will control the risk.

If no material assumption is required, state `None`.
```

Purpose: show what information the model determined was relevant, where it looked, what it established and what remains unproven. Avoidable uncertainty must be investigated before solution selection.

## Question 3 — Concrete candidate solutions

```markdown
### 3. What concrete solutions are supported by the available evidence?

A proposed solution is valid only if it:

- satisfies every applicable hard constraint;
- states exact, implementable changes;
- explains why those exact changes were selected;
- identifies which parts of the problem it is expected to resolve;
- supports its expected coverage with evidence;
- includes an implementation sequence;
- addresses compatibility and maintainability;
- identifies remaining risks or execution-dependent evidence;
- can be evaluated against the authoritative requirements.

Do not submit a vague direction such as "upgrade the framework" or "update the
dependencies." State the exact proposed change, the evidence supporting it and
how it is expected to resolve the identified problem.

For every candidate solution, answer:

| Question | Model answer |
|---|---|
| What exact solution is proposed? | |
| What evidence supports this solution? | |
| Which parts of the problem will it resolve? | |
| Does it comply with all applicable requirements? | |
| How will it be implemented? | |
| How will compatibility be preserved? | |
| Why is the result maintainable? | |
| What risks or unknowns remain? | |
| How will the result be validated against the authoritative requirements? | |
| Is it a COMPLETE or PARTIAL solution? | |

A solution known to violate a constraint must not be presented as a candidate.

A PARTIAL solution may be considered only when no evidence-supported COMPLETE
solution is currently available, it violates no constraint, it provides safe
measurable progress, it does not unnecessarily prevent later complete resolution,
and it explicitly identifies what remains unresolved.
```

A candidate solution must be implementable. It must specify concrete versions, configurations, ownership boundaries, source changes, exclusions or other modifications when those details are required to define the solution. A general direction is not a candidate solution.

## Question 4 — Selection

```markdown
### 4. Which solution is selected, and why is it preferred?

State:

- the selected solution;
- whether it is COMPLETE or PARTIAL;
- why it is preferred;
- why it provides better complete-problem coverage than the other candidates;
- its remaining risks;
- the evidence that would require reconsidering the selection.
```

Implementation is not repeated here because each candidate already contains an implementation sequence.

---

# 6. Pre-execution decision-journal template

The orchestrator writes the canonical task. The model supplies only the Model Response answers.

```markdown
# Cycle <N> — Problem Analysis and Solution Decision

> This cycle record captures the decision state before implementation begins.
>
> The first section contains the task and requirements supplied by the system.
>
> The second section contains the model's response: what it understands it has
> been asked to accomplish, the information it needed and established, the
> evidence-supported solutions it developed, and the solution it selected.
>
> Keeping both sections in one record allows implementation, validation, later
> cycles and human reviewers to compare the original requirement with the
> model's understanding and decision.

## Task to Solve

### What is the task, and what must the final result satisfy?

<Exact canonical task block supplied to the model>

## Model Response

### 1. What does the model understand it has been asked to accomplish?

<Model answer>

### 2. What information was needed to develop an evidence-supported solution,
and what did the model find?

<Model answer>

### 3. What concrete solutions are supported by the available evidence?

<Model answer>

### 4. Which solution is selected, and why is it preferred?

<Model answer>
```

The model must not directly edit this file. The orchestrator renders accepted model answers safely so model-provided headings cannot corrupt the document structure.

---

# 7. Transition to implementation

After the pre-execution response is accepted, implementation capabilities become available. The same model session continues when possible.

```text
The pre-execution Model Response was accepted.

Proceed with implementation of the selected solution.

Continue evaluating new evidence against the complete Task to Solve and its
requirements. If evidence invalidates the selected solution, reassess and retain,
revise, extend, replace or combine solutions as justified.

Continue while time and operational budget remain. Before ending execution,
perform the available self-validation and provide a concise execution summary.
The orchestrator will request the mandatory post-execution result separately.
```

No optional strategy-checkpoint tool or additional workflow phase is introduced.

When evidence materially changes the selected solution, the model adapts during normal implementation. The mandatory post-execution record later captures:

- the solution actually implemented;
- changes from the pre-execution selection;
- new evidence;
- rejected assumptions;
- attempted and abandoned approaches;
- self-validation;
- requirement coverage;
- unresolved work.

---

# 8. Relationship to later cycles

Every later cycle receives:

1. the same canonical `Task to Solve`;
2. prior pre-execution answers;
3. actual changes and command evidence;
4. the prior post-execution result;
5. independent deterministic validation;
6. unresolved requirements.

The next cycle must audit prior evidence rather than automatically continue the previous solution. It remains free to retain, revise, extend, replace, combine or independently investigate solutions.

The canonical task does not change merely because a previous cycle misunderstood it.

---

# 9. Implementation guardrails

When implementing this design:

- Preserve the current single-session flow.
- Preserve mandatory pre-execution and post-execution submissions.
- Preserve independent deterministic validation.
- Do not add optional decision or strategy checkpoints.
- Do not create an additional approval or orchestration phase.
- Do not duplicate the run-specific task in stable instructions.
- Do not allow model-authored text to redefine authoritative requirements.
- Do not hardcode technology-specific rules into the generic operating instructions.
- Keep continuation context bounded and report truncation truthfully.
- Treat missing model-authored information as a capture-quality issue; reconstruct later-cycle evidence from task data, project state, changes, commands and validation when possible.

---

# 10. Current implementation mapping

The existing architecture already provides the required high-level sequence:

- the model is created with stable agent instructions;
- the orchestrator builds the first run-specific message;
- one persistent session is retained;
- pre-execution submission gates material capabilities;
- accepted submission enables implementation in the same turn;
- post-execution reporting occurs in a separate metadata-only turn;
- deterministic validation runs afterward.

The intended implementation should therefore refine prompt content, questionnaire fields and journal rendering without replacing the established control flow.
