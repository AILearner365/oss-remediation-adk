# Pre-Execution Prompt and Decision-Journal Design

## Scope

This document is the agreed design reference for the first, pre-execution stage of a problem-solving cycle.

It contains only:

1. the stable operating instructions supplied to the model;
2. the canonical run-specific task supplied on the first request;
3. the instruction that tells the model how to complete the pre-execution analysis;
4. the ordered questionnaire and answer requirements;
5. the corresponding pre-execution section rendered into `decision-journal.md`.

This design replaces the content currently described as Cycle Intent. It does not change the existing workflow sequence or define the later post-execution template. Implementation reassessment, post-execution reporting, deterministic validation, and later-cycle templates will be designed separately.

The existing control flow remains:

```text
Create one model session
        ↓
Send the first cycle request
        ↓
Perform read-only investigation
        ↓
Submit the required pre-execution analysis and solution decision
        ↓
Existing workflow continues
```

This document defines the content and structure of that first submitted record.

---

# 1. How the first request is assembled

The first request seen by the model consists of three connected parts:

1. **Stable operating instructions** — how the model must work.
2. **Task to Solve** — the exact run-specific problem and requirements.
3. **Pre-execution instruction and questionnaire** — what the model must investigate, answer, and submit before material changes.

These are prompt components, not separate workflow stages.

The run-specific task must appear once as the canonical source of truth. It must not be independently paraphrased into conflicting problem statements elsewhere in the prompt.

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
- Respect every supplied constraint. Treat each hard constraint as a mandatory
  candidate-admissibility condition, not a preference or optimization criterion.
  Only candidates whose hard-constraint compatibility is established sufficiently
  for selection may be compared, selected or implemented.
- Use available context, files, relationships, commands, tools, validation
  evidence and permitted authoritative information sources to investigate
  decision-critical facts.
- Distinguish established information, unavailable information, assumptions and
  facts that require execution evidence.
- Do not present an assumption as an established fact.
- Establish candidate-relevant facts from Task-to-Solve content, directly
  observed repository state and observed execution results before reconciling
  hard constraints. Treat that evidence as stronger than unsupported prior
  expectations, conventions, interpretations or guesses. Use expectations to
  identify discrepancies for investigation, not to change established properties
  of a proposed operation without additional supporting evidence.
- Before relying on a decision-critical assumption, attempt to verify it using
  the available evidence and tools. An assumption cannot override established
  evidence, waive a hard constraint or make a conflicting candidate admissible.
- When solution choice depends on how relevant state or behavior is produced or
  controlled, investigate the existing ownership, control, management,
  inheritance, indirection, configuration, composition, abstraction or
  relationships to the depth reasonably necessary for the decision. Treat that
  existing structure as engineering evidence.
- Prefer a focused, coherent and maintainable intervention through an appropriate
  existing control point when evidence supports it, rather than introducing a
  lower-level, parallel or redundant mechanism merely because it can work.
  Repository evidence, not a universal hierarchy, determines the appropriate
  intervention point.
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
- a solution order;
- a project-specific command;
- a vulnerability-specific recipe.

Those details must come from the run-specific task, available evidence and the model's analysis.

---

# 3. Canonical Task to Solve

The run-specific task is assembled from one normalized source of truth using:

- the submitted request;
- prepared source and reference information;
- the current working location;
- baseline findings;
- configured commands;
- supplied constraints;
- configured validation behavior.

The same canonical task representation must be:

1. supplied to the model;
2. rendered into the pre-execution decision journal;
3. retained as the unmodified task reference for the run.

The model must not regenerate or rewrite this section.

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

## Task-rendering rules

Requirement rows are dynamic. Only applicable requirements are rendered.

- Requested scope controls the target-resolution requirement.
- The prohibited-new-finding configuration controls the no-regression requirement.
- Configured build, test and startup commands produce concrete validation requirements.
- Suppression policy produces a concrete constraint when configured.
- Version policy is rendered as its exact allowed and prohibited movement.
- Protected values and allowed or protected paths are rendered when configured.
- Other supplied engineering constraints are rendered without changing their meaning.
- A constraint that was not supplied must not be invented.
- Generic engineering requirements may remain stable, but their evaluation method must not be falsely described as deterministic when it requires evidence-based assessment.

The task section is the question paper supplied by the system. It is not a model answer.

---

# 4. Pre-execution instruction

The first request must explain why the model is answering the questionnaire and what quality is expected.

```text
You are expected to implement and validate a solution for the Task to Solve.

Before making the first material change:

1. investigate the supplied task and relevant evidence;
2. answer every Model Response question below;
3. develop only concrete, evidence-supported solutions;
4. ensure every proposed solution satisfies every applicable hard constraint;
5. select the solution you currently intend to implement;
6. submit the completed pre-execution Model Response through the required
   capability.

This is the decision record for the solution you intend to implement. It is not
a documentation-only exercise and it is not a request for vague or hypothetical
directions.

Use read-only investigation before submission. Investigate avoidable uncertainty
before proposing solutions. When a fact cannot be established until execution,
identify it explicitly as execution-dependent evidence rather than presenting it
as established.

Do not rewrite the Task to Solve. Answer the Model Response questions using the
task, available context and evidence.
```

---

# 5. Model Response questionnaire

The model must answer the following four questions in this order.

---

## Question 1 — Model understanding

### Question supplied to the model

```markdown
### 1. What does the model understand it has been asked to accomplish?
```

### Answer instructions supplied to the model

```text
Explain:

- the requested result;
- the target scope;
- the requirements that materially govern the work;
- what constitutes complete resolution.

Use your own concise wording so that your understanding can be compared with the
Task to Solve.

Do not propose or select a solution in this answer.
Do not replace, narrow or expand the authoritative task.
```

### Expected journal answer shape

```markdown
### 1. What does the model understand it has been asked to accomplish?

<Model answer describing the requested result, scope, governing requirements and
meaning of complete resolution>
```

Purpose: make misunderstanding visible before solution selection without allowing the model's interpretation to replace the canonical task.

---

## Question 2 — Information, investigation and remaining uncertainty

### Question supplied to the model

```markdown
### 2. What information was needed to develop an evidence-supported solution,
and what did the model find?
```

### Answer instructions supplied to the model

```text
Identify the information required to develop a concrete solution for this task.

For every decision-relevant information category, state:

- what information was needed;
- why it was needed;
- which sources, tools or methods were examined;
- what was found;
- what remains unknown or requires execution evidence.

Use this table:

| Information needed | Why it was needed | Sources examined | Finding | What remains unknown or requires execution |
|---|---|---|---|---|

The Sources examined column must identify actual evidence sources or investigation
methods. Do not claim that information was verified without identifying its
source.

Before reconciling candidates with hard constraints, establish candidate-relevant
facts from the Task to Solve, directly observed repository state and observed
execution evidence. Distinguish those established facts from interpretations,
unresolved uncertainty, prior knowledge, expectations, conventions or guesses.
The latter may identify a decision-critical discrepancy to investigate, but must
not displace stronger task-specific or observed evidence unless additional
evidence establishes that the observed interpretation is wrong, incomplete or not
applicable. The established properties of a proposed change govern constraint
reconciliation; describing or rationalizing the change differently does not alter
those properties.

Distinguish ordinary execution-dependent uncertainty from uncertainty that
materially determines hard-requirement or hard-constraint compliance. Ordinary
uncertainty such as whether builds, tests or runtime checks succeed may remain
for implementation and validation. Investigate hard-constraint-determining
uncertainty before candidate selection when reasonably possible using available
read-only evidence. If it cannot be resolved sufficiently for selection, preserve
it honestly: the affected candidate is not yet admissible and the uncertainty
must not be converted into an assumption that permits selection.

When solution choice materially depends on how relevant state or behavior is
produced or controlled, investigate the existing ownership, control, management,
inheritance, indirection, configuration, composition, abstraction, relationships
or other repository-evidenced mechanisms to the depth reasonably necessary for
the decision. Treat that structure as engineering evidence. Prefer a coherent
intervention through an appropriate existing control point when evidence supports
it rather than introducing a lower-level, parallel or redundant mechanism merely
because it can work; repository evidence determines the appropriate point.

Finding one workable mechanism is not sufficient reason to stop investigation.
Before forming candidates, investigate materially different solution mechanisms
reasonably suggested by task or repository evidence when they could materially
affect correctness, requirement or constraint satisfaction, compatibility,
maintainability, scope or engineering coherence. Actively seek more than one
materially distinct credible solution when the evidence reasonably suggests
alternatives, while keeping investigation evidence-driven and proportional.
Unsupported, unavailable, infeasible or constraint-conflicting possibilities do
not need to become candidates.

After the table, identify only assumptions that materially affect the current
engineering decision. For each assumption, state:

- what is being assumed;
- why the information could not be established;
- what evidence was already checked;
- which decision or conclusion depends on the assumption;
- what uncertainty or risk remains.

Do not introduce an assumption merely to explain unexpected evidence or justify
proceeding. If an unresolved interpretation is not necessary to the decision,
leave it as uncertainty rather than elevating it into a material assumption.

If no material assumption is required, state: None.

Investigate avoidable uncertainty before solution selection. Keep assumptions
limited and explicit.
```

### Expected journal answer shape

```markdown
### 2. What information was needed to develop an evidence-supported solution,
and what did the model find?

| Information needed | Why it was needed | Sources examined | Finding | What remains unknown or requires execution |
|---|---|---|---|---|
| <information> | <reason> | <actual sources or methods> | <finding> | <remaining gap> |

#### Material assumptions that remain necessary

- <Assumption and supporting explanation>

Or:

None.
```

Purpose: capture what information the model determined was necessary, what it actually investigated, what evidence it found and what remains unproven. This replaces disconnected context, evidence, uncertainty and assumption sections.

---

## Question 3 — Concrete candidate solutions

### Question supplied to the model

```markdown
### 3. What concrete solutions are supported by the available evidence?
```

### Answer instructions supplied to the model

```text
Develop only solutions that are concrete enough to implement.

Candidate count is the result of investigation, not the target that determines
investigation breadth. If multiple materially distinct solutions remain genuinely
evidence-supported, preserve them as separate candidates and compare them. If
only one viable candidate remains, one candidate is valid. When task or repository
evidence reasonably suggested other materially plausible mechanisms, briefly
identify which were investigated or considered and why they were eliminated,
unsupported, unavailable, infeasible, constraint-conflicting or otherwise did not
qualify as candidates; never manufacture alternatives merely to satisfy a count.

Hard constraints are mandatory candidate-admissibility conditions, not preferences
to balance against engineering benefits. For each proposed mechanism, first
establish its constraint-relevant properties from the Task to Solve and available
repository, tool and execution evidence; then reconcile those properties against
every applicable hard requirement and constraint. Only candidates with
hard-constraint compatibility established sufficiently for selection are
admissible for COMPLETE or PARTIAL classification and engineering comparison. An
established conflict makes a mechanism ineligible for selection or implementation.
Materially unresolved hard-constraint compatibility makes it not yet admissible
and requires further investigation before selection. Neither an assumption nor a
different description, interpretation or rationale for the same established
operation can waive a hard constraint or make it admissible.

A constraint-conflicting mechanism may still be investigated and recorded as
eliminated; investigation is not restricted to admissible solutions. Once the
conflict is established, do not promote that mechanism into a selectable
candidate. PARTIAL is not a mechanism for bypassing unresolved hard-constraint
compliance; it remains valid for safe, evidence-supported, constraint-compliant
progress with unresolved completeness, remaining work or ordinary
execution-dependent uncertainty.

A proposed solution is valid only if it:

- satisfies every applicable hard constraint;
- states exact, implementable changes;
- explains why those exact changes were selected;
- identifies which parts of the problem it is expected to resolve;
- supports its expected coverage with evidence;
- includes an ordered implementation sequence;
- addresses compatibility and maintainability;
- identifies remaining risks or execution-dependent evidence;
- can be evaluated against the requirements in the Task to Solve.

Do not submit a vague direction such as "upgrade the framework", "update the
dependencies", "change the configuration" or "refactor the code". State the exact
proposed versions, configurations, ownership boundaries, source changes,
exclusions or other modifications needed to define the solution.

For every candidate, use the following structure:

#### Candidate Solution <identifier> — <specific solution name>

| Question | Model answer |
|---|---|
| What exact solution is proposed? | <Exact implementable changes> |
| Why were these exact changes selected? | <Evidence-based rationale> |
| What evidence supports the expected result? | <Evidence sources and conclusions> |
| Which parts of the problem will it resolve? | <Complete coverage or explicit partial coverage> |
| Does it satisfy every applicable requirement? | <Evaluate the applicable requirement IDs; every hard constraint must be satisfied> |
| How will it be implemented? | <Ordered implementation sequence> |
| How will compatibility be preserved? | <Compatibility basis and execution-dependent checks> |
| Why is the result coherent and maintainable? | <Ownership and maintainability explanation> |
| What risks or unknowns remain? | <Conditions that could invalidate or alter the solution> |
| How will the result be validated? | <Applicable task requirements and solution-specific checks> |
| Is it a COMPLETE or PARTIAL solution? | <Classification and justification> |

A solution known to violate a hard constraint must not be presented as a candidate.

A solution may be classified COMPLETE only when the available evidence supports
a credible route to every required result, subject to identified execution
validation.

A PARTIAL solution may be included only when:

- no evidence-supported COMPLETE solution is currently available;
- it violates no constraint;
- it provides safe, measurable progress;
- it does not unnecessarily prevent later complete resolution;
- it precisely identifies what remains unresolved.

Do not invent additional candidates merely to create alternatives. Include the
concrete solutions genuinely supported by the evidence.
```

### Expected journal answer shape

```markdown
### 3. What concrete solutions are supported by the available evidence?

#### Candidate Solution A — <specific solution name>

| Question | Model answer |
|---|---|
| What exact solution is proposed? | <answer> |
| Why were these exact changes selected? | <answer> |
| What evidence supports the expected result? | <answer> |
| Which parts of the problem will it resolve? | <answer> |
| Does it satisfy every applicable requirement? | <answer> |
| How will it be implemented? | <answer> |
| How will compatibility be preserved? | <answer> |
| Why is the result coherent and maintainable? | <answer> |
| What risks or unknowns remain? | <answer> |
| How will the result be validated? | <answer> |
| Is it a COMPLETE or PARTIAL solution? | <answer> |

<Repeat only for other evidence-supported candidate solutions>
```

Purpose: require definitive proposed solutions rather than high-level directions. Each candidate includes its own implementation plan, so no separate implementation-plan question is needed.

---

## Question 4 — Selected solution

### Question supplied to the model

```markdown
### 4. Which solution is selected, and why is it preferred?
```

### Answer instructions supplied to the model

```text
State:

- the selected candidate solution;
- whether it is COMPLETE or PARTIAL;
- why it is preferred for this task and evidence;
- why it provides better complete-problem coverage than the other candidates;
- its material remaining risks;
- the evidence that would require reconsidering the selection.

Do not repeat the complete implementation sequence. It is already recorded in
the selected candidate.

Confirm hard-constraint admissibility before applying preference. Compare only
admissible candidates using current evidence, problem coverage, compatibility,
coherence, maintainability, scope and risk. These engineering qualities cannot
outweigh a hard-constraint conflict. Do not select a solution only because it
appears fastest or easiest. Do not select a candidate with an established
hard-requirement or hard-constraint conflict, or one whose compliance remains
materially unresolved or depends on an assumption, regardless of whether it is
labeled COMPLETE or PARTIAL. Ordinary execution-dependent results that do not
determine hard-constraint compliance may remain for implementation,
self-validation and deterministic validation.
```

### Expected journal answer shape

```markdown
### 4. Which solution is selected, and why is it preferred?

- **Selected solution:** <candidate identifier and name>
- **Classification:** COMPLETE or PARTIAL
- **Why it is preferred:** <answer>
- **Comparative coverage:** <answer>
- **Remaining risks:** <answer>
- **Evidence requiring reconsideration:** <answer>
```

Purpose: record the decision without repeating the candidate's detailed solution and implementation plan.

---

# 6. Complete pre-execution journal template

The following is the complete agreed template for the first record in a cycle.

The orchestrator renders the `Task to Solve` from the canonical task data. The model supplies the four accepted answers. Both are placed in the same journal document.

```markdown
# Cycle <N> — Problem Analysis and Solution Decision

> This record captures the decision state before implementation begins.
>
> The first section contains the task and requirements supplied by the system.
>
> The second section contains the model's response: what it understands it has
> been asked to accomplish, the information it needed and established, the
> evidence-supported solutions it developed, and the solution it selected.
>
> Keeping both sections in one record allows the model, later validation, later
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

| Information needed | Why it was needed | Sources examined | Finding | What remains unknown or requires execution |
|---|---|---|---|---|
| <information> | <reason> | <actual sources or methods> | <finding> | <remaining gap> |

#### Material assumptions that remain necessary

<Model answer or None>

### 3. What concrete solutions are supported by the available evidence?

#### Candidate Solution A — <specific solution name>

| Question | Model answer |
|---|---|
| What exact solution is proposed? | <answer> |
| Why were these exact changes selected? | <answer> |
| What evidence supports the expected result? | <answer> |
| Which parts of the problem will it resolve? | <answer> |
| Does it satisfy every applicable requirement? | <answer> |
| How will it be implemented? | <answer> |
| How will compatibility be preserved? | <answer> |
| Why is the result coherent and maintainable? | <answer> |
| What risks or unknowns remain? | <answer> |
| How will the result be validated? | <answer> |
| Is it a COMPLETE or PARTIAL solution? | <answer> |

<Repeat only for other evidence-supported candidates>

### 4. Which solution is selected, and why is it preferred?

- **Selected solution:** <candidate identifier and name>
- **Classification:** COMPLETE or PARTIAL
- **Why it is preferred:** <answer>
- **Comparative coverage:** <answer>
- **Remaining risks:** <answer>
- **Evidence requiring reconsideration:** <answer>
```

---

# 7. Capture and rendering requirements

The pre-execution record must satisfy these structural rules:

- The canonical `Task to Solve` is system-rendered and cannot be overwritten by the model.
- All four Model Response questions are required.
- Question 2 must identify actual evidence sources or investigation methods.
- Every material assumption must be explicit, or the answer must state `None`.
- Every candidate must contain all required candidate fields.
- Every candidate must satisfy all applicable hard constraints.
- Candidate classification must be either `COMPLETE` or `PARTIAL`.
- The selected solution must reference one of the submitted candidates.
- A selected PARTIAL solution must explain why no supported COMPLETE solution is currently available.
- Model-authored content must be rendered as data so embedded headings cannot escape or corrupt the journal structure.
- Missing or structurally incomplete answers must be returned to the model for correction before material capabilities are enabled.
- Structural acceptance does not prove semantic correctness. Later execution evidence and independent validation remain separate.

---

# 8. Current implementation relationship

The existing implementation already:

- creates one persistent model session;
- sends stable instructions through the agent definition;
- constructs a run-specific first message;
- restricts initial capabilities to read-only investigation;
- requires a pre-execution submission;
- unlocks material capabilities after accepted submission;
- renders the accepted data into `decision-journal.md`.

Implementation of this design should therefore replace and restructure the current Cycle Intent content without replacing the existing workflow sequence.

This document intentionally stops at acceptance of the pre-execution analysis and solution decision. The later implementation/reassessment record, post-execution questionnaire, deterministic-validation presentation and next-cycle prompt are outside its current scope.
