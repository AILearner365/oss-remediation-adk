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
Perform investigation in the isolated cycle experiment
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
3. synthesize the project-applicable engineering considerations and high-level solution space;
4. develop concrete, evidence-supported solutions;
5. select a solution;
6. implement it;
7. reassess it when execution produces new evidence;
8. self-validate the resulting work;
9. submit an honest post-execution result.

Operating principles:

- Treat the supplied Task to Solve and its requirements as the source of truth.
- Respect every supplied constraint. Treat each hard constraint as a mandatory
  candidate-admissibility condition, not a preference or optimization criterion.
  Only candidates whose hard-constraint compatibility is established sufficiently
  for selection may be compared, selected or implemented.
- Before forming candidates, perform decision-relevant investigation reasonably
  obtainable through the available engineering capabilities. When a material
  decision depends on information that may have changed outside the repository,
  obtain reasonably available current authoritative evidence and use it to
  discover the actual available and potentially applicable solution space, not
  merely to confirm the first preferred solution. Planned or future investigation
  is not evidence supporting candidate formation; non-material questions need not
  be pursued, and genuinely execution-dependent outcomes remain for implementation
  and validation.
- Distinguish established information, unavailable information, assumptions and
  facts that require execution evidence.
- Do not present an assumption as an established fact.
- Establish candidate-relevant facts from Task-to-Solve content, directly
  observed repository state and observed execution results before reconciling
  hard constraints. Treat that evidence as stronger than unsupported or
  potentially stale prior expectations, conventions, interpretations or guesses.
  Current external evidence may establish what options exist and their documented
  properties, but does not by itself override what the task, repository or
  execution establishes for this project. Use discrepancies to direct further
  investigation rather than to invalidate observed project facts without evidence.
- Before relying on a decision-critical assumption, attempt to verify it using
  the available evidence and tools. An assumption cannot override established
  evidence, waive a hard constraint or make a conflicting candidate admissible.
- When solution choice depends on how relevant state or behavior is produced or
  controlled, investigate the existing ownership, control, management,
  inheritance, indirection, configuration, composition, abstraction or
  relationships to the depth reasonably necessary for the decision. General
  technical knowledge may suggest a mechanism to investigate, but when
  repository-specific evidence is material and reasonably obtainable, establish
  that the mechanism applies, participates in controlling the relevant state and
  has an evidence-supported basis for the intended effect.
- Use current external evidence to establish which options exist and can provide
  the required outcome, and repository or experimental evidence to establish which
  mechanisms are applicable and sufficiently compatible for this project.
  Synthesize that evidence through the rationale of relevant engineering
  principles, established practices, ownership or control boundaries, architecture,
  constraints, support and compatibility to derive the project-applicable
  high-level solution space before concrete candidates. Do not treat a generic
  best practice or the newest option as automatically correct. Preference among
  viable mechanisms belongs after viability determination.
- Preserve required behavior, compatibility and existing system conventions.
- Do not make unnecessary or unrelated changes.
- Before final selection, challenge whether the leading candidate is merely
  workable or is the strongest project-fit solution reasonably supported by the
  available evidence. Investigate and reconsider when a materially unresolved
  decision issue and reasonably obtainable evidence could materially change
  selection; otherwise proceed without exhaustive exploration or proof of a
  global optimum.
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

Use the isolated cycle experiment and other available engineering capabilities before submission. Investigate avoidable uncertainty
before proposing solutions. When a fact cannot be established until execution,
identify it explicitly as execution-dependent evidence rather than presenting it
as established.

Do not rewrite the Task to Solve. Answer the Model Response questions using the
task, available context and evidence.
```

---

# 5. Model Response questionnaire

The model must answer the following five questions in this order. The answers capture the final pre-selection decision state; their order is a diagnostic boundary, not a rigid reasoning waterfall.

---

## Question 1 — Problem understanding in project context

### Question supplied to the model

```markdown
### 1. What engineering problem is currently established in the context of this project?
```

### Answer instructions supplied to the model

```text
Explain proportionally:

- the requested result;
- the target scope;
- the requirements and constraints that materially govern the work;
- project characteristics material to understanding the problem;
- material relationships among symptoms or components when supported by evidence;
- what constitutes complete resolution.

Use your own concise wording so that your understanding can be compared with the
Task to Solve.

Do not require or assert a shared or higher-level root cause before the evidence supports one.
Do not propose solutions, enumerate approaches or select mechanisms in this answer.
Do not replace, narrow or expand the authoritative task.
```

### Expected journal answer shape

```markdown
### 1. What engineering problem is currently established in the context of this project?

<Model answer describing the requested result, scope, governing requirements,
material project context and meaning of complete resolution>
```

Purpose: make project-context problem misunderstanding visible before solution selection without requiring a premature root-cause conclusion or allowing the model's interpretation to replace the canonical task.

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

The table must report investigation actually performed and evidence actually
obtained. The Sources examined column must identify actual evidence sources or
investigation methods. Planned, intended, future or not-yet-performed investigation
is not a finding and is not evidence supporting candidate formation. Select
evidence sources and mechanisms according to the proposition being established
rather than treating any single capability as the universal research mechanism.
Distinguish failure, unavailability, inconclusive results and unusable output from
evidence that establishes the investigated fact or establishes absence. A failed
or inconclusive mechanism leaves the fact unresolved: it is not evidence for or
against the proposition and does not justify substituting unsupported prior
knowledge, convention, expectation or assumption. If the unresolved fact is
decision-critical and another appropriate mechanism available through the existing
engineering capabilities could materially resolve it, investigate through a
reasonable alternative before candidate selection. This does not require trying
every mechanism, following a fixed fallback sequence or redundantly confirming a
fact after sufficient decision-relevant evidence exists.

If decision-relevant information is reasonably obtainable through the available
engineering capabilities and could materially affect problem understanding,
mechanism discovery or applicability, control structure, viability, constraints,
candidate formation or selection, investigate it before submitting this response.
When that information may have changed outside the repository, obtain reasonably
available current authoritative evidence and use it to discover the actual
available and potentially applicable solution space rather than merely confirming
the first preferred solution. Prefer current primary or authoritative sources
when reasonably available for material externally changing claims; when obtained,
that evidence takes precedence over unsupported or potentially stale prior
knowledge about the changing fact. Current external evidence may establish what
options and documented properties currently exist; repository and execution
evidence establish what applies to and happens in this project. Failed, blocked,
incomplete or inconclusive research is not evidence of absence. Uncertainty is
not evidence for or against an approach. If no reasonable available mechanism can
obtain sufficient evidence, preserve the uncertainty honestly. Keep investigation
proportional; non-material information does not require exhaustive investigation,
and genuinely execution-dependent information may remain unknown.

Before reconciling candidates with hard constraints, establish candidate-relevant
facts from the Task to Solve, directly observed repository state and observed
execution evidence. Distinguish those established facts from interpretations,
unresolved uncertainty, assumptions, prior knowledge, expectations, conventions
or guesses.
The latter may identify a decision-critical discrepancy to investigate, but must
not displace stronger task-specific or observed evidence unless additional
evidence establishes that the observed interpretation is wrong, incomplete or not
applicable. Do not use an unsupported expectation, convention, potentially stale
prior, unresolved assumption or absence of evidence as positive support or as a
material reason to eliminate a plausible approach. The established properties of a proposed change govern constraint
reconciliation; describing or rationalizing the change differently does not alter
those properties.

Distinguish ordinary execution-dependent uncertainty from uncertainty that
materially determines hard-requirement or hard-constraint compliance. Ordinary
uncertainty such as whether builds, tests or runtime checks succeed may remain
for implementation and validation; candidate formation requires an
evidence-supported basis for trying a mechanism, not pre-execution proof of those
outcomes. Investigate hard-constraint-determining uncertainty before candidate
selection when reasonably possible using the available investigation capabilities. If it
cannot be resolved sufficiently for selection, preserve it honestly: the affected
candidate is not yet admissible and the uncertainty must not be converted into an
assumption that permits selection.

When solution choice materially depends on how relevant state or behavior is
produced or controlled, investigate the existing ownership, control, management,
inheritance, indirection, configuration, composition, abstraction, relationships
or other repository-evidenced mechanisms to the depth reasonably necessary for
the decision. Record evidence about those boundaries here; the engineering
conclusion derived from it belongs in Question 3. If candidate viability or
selection materially depends on a repository-specific premise that a proposed
mechanism controls, changes, resolves, produces or otherwise affects relevant
state or behavior, and the available isolated investigation capabilities can
reasonably test that premise, obtain sufficient evidence before treating it as
established or sufficiently supported for selection. General technical knowledge
may suggest the premise to investigate, but does not establish repository-specific
applicability when material project evidence is reasonably obtainable. If
sufficient evidence cannot reasonably be obtained, record the premise and the
affected approach as unresolved; that uncertainty neither supports the candidate
nor establishes that the mechanism is non-viable. This
requires decision-sufficient support, not exhaustive pre-execution proof, testing
every candidate, running every validation or proving final task success.

After the table, identify only assumptions that materially affect the current
engineering decision. For each assumption, state:

- what is being assumed;
- why the information could not be established;
- what evidence was already checked;
- which decision or conclusion depends on the assumption;
- what uncertainty or risk remains.

An assumption must not substitute for reasonably obtainable repository evidence
material to candidate formation or selection.

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

## Question 3 — Project-applicable engineering synthesis and high-level solution space

### Question supplied to the model

```markdown
### 3. What project-applicable engineering synthesis and high-level solution space follow from the established evidence?
```

### Answer instructions supplied to the model

```text
Identify only the engineering principles, established practices, ownership or
control boundaries, architectural relationships, support or compatibility
boundaries and other considerations that materially shape this decision.

Explain why the rationale behind each consideration matters to this problem and
project. Do not invoke generic best practice as an unconditional rule. Use the
project architecture, ownership and control evidence, constraints, current
authoritative information when material, and repository or experimental evidence
to determine whether a generally applicable consideration should be retained
as-is, adapted, rejected for this project or left uncertain. The newest option is
not automatically correct.

From that synthesis, derive the materially distinct high-level solution approaches
reasonably supported by the evidence. Question 2's evidence record is the
evidentiary boundary for this synthesis; do not invent missing support here.
Distinguish viability from preference. Do not eliminate an approach merely because
another appears preferable. Uncertainty is not evidence. Do not materially
eliminate a plausible approach when the deciding reason is an unsupported
expectation, convention, potentially stale prior, unresolved assumption or absence
of evidence; preserve its unresolved viability instead. An approach may be
eliminated when observed task, repository or execution evidence, current
authoritative information or a hard task constraint materially establishes the
reason. Record evidence-based elimination or unresolved viability when material.
One approach is valid when evidence eliminates the others; there is no
minimum approach count and alternatives must not be manufactured.

Keep the answer proportional. Do not repeat the investigation log, list generic
practices without project-specific rationale, exhaustively catalog theoretical
solutions, specify exact file/version/configuration edits, provide an
implementation plan or candidate-level validation, compare concrete candidates,
select a solution or expose private chain-of-thought.
```

### Expected journal answer shape

```markdown
### 3. What project-applicable engineering synthesis and high-level solution space follow from the established evidence?

<Concise project-applicable synthesis, followed by the materially distinct
high-level approaches and any material evidence-based elimination or uncertainty>
```

Purpose: expose how established evidence was transformed into the project-applicable solution space without recording private chain-of-thought or prematurely specifying implementation details.

---

## Question 4 — Concrete candidate solutions

### Question supplied to the model

```markdown
### 4. What concrete solutions translate the surviving high-level approaches into implementable changes?
```

### Answer instructions supplied to the model

```text
Translate the surviving high-level approaches into solutions concrete enough to implement.

Form candidates only from decision-relevant investigation actually performed and
evidence actually obtained. Planned investigation or general technical
plausibility alone does not establish repository-specific applicability or
viability. If candidate viability or COMPLETE classification materially depends
on a repository-specific premise that isolated investigation can reasonably test,
obtain sufficient evidence before treating the premise as established. If
sufficient evidence cannot reasonably be obtained, preserve the premise and
high-level approach as unresolved; do not promote the premise into candidate
support, and do not treat it as evidence that the approach is non-viable. This is
a decision-sufficient standard, not a requirement to prove final success or test
every candidate experimentally.

Candidate count is the result of investigation and synthesis, not a target that
determines their breadth. Preserve materially distinct surviving high-level
approaches as separate concrete candidates when appropriate and admissible, even
when another candidate appears preferable. If only one viable candidate remains
after evidence-based approach elimination, one candidate is valid. Do not repeat
high-level elimination reasoning here unless it is necessary for a candidate-
specific admissibility decision. Relative preference alone is not an elimination
reason. Never manufacture alternatives merely to satisfy a count.

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
### 4. What concrete solutions translate the surviving high-level approaches into implementable changes?

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

## Question 5 — Selected solution

### Question supplied to the model

```markdown
### 5. Which solution is selected, and why is it preferred?
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

Before committing, challenge whether the leading candidate is merely workable or
is the strongest project-fit solution reasonably supported by the available
evidence. Recheck whether project evidence, structure, constraints or engineering
synthesis imply a materially distinct plausible approach that was not reasonably
considered, and whether unsupported assumptions, expectations, conventions,
potentially stale priors, unresolved facts or absence of evidence were used to
eliminate an approach. If this reveals a materially unresolved decision issue and
reasonably obtainable investigation could materially change selection, investigate
and revise the synthesis or candidates before completing selection. Otherwise
proceed.

This is a proportional search-sufficiency check, not a requirement to prove a
global optimum, exhaustively explore, manufacture or score alternatives, or submit
multiple candidates. One candidate remains valid when evidence genuinely
eliminates the alternatives. Concisely explain the important approaches considered
or eliminated, the evidence supporting material eliminations, and why remaining
uncertainty does not require further pre-selection investigation.

Do not repeat the complete implementation sequence. It is already recorded in
the selected candidate.

Confirm hard-constraint admissibility before applying preference. Compare the
surviving admissible candidates using current evidence, problem coverage,
compatibility, coherence, maintainability, scope and risk. Apply these engineering
preferences here, after candidate formation; do not use them to retroactively
exclude a viable candidate. These qualities cannot outweigh a hard-constraint
conflict. Do not select a candidate with an established
hard-requirement or hard-constraint conflict, or one whose compliance remains
materially unresolved or depends on an assumption, regardless of whether it is
labeled COMPLETE or PARTIAL. Ordinary execution-dependent results that do not
determine hard-constraint compliance may remain for implementation,
self-validation and deterministic validation.
```

### Expected journal answer shape

```markdown
### 5. Which solution is selected, and why is it preferred?

- **Selected solution:** <candidate identifier and name>
- **Classification:** COMPLETE or PARTIAL
- **Why it is preferred:** <answer>
- **Comparative coverage:** <answer>
- **Remaining risks:** <answer>
- **Evidence requiring reconsideration:** <answer>
```

Purpose: challenge whether exploration is sufficient, then record the final decision without repeating the candidate's detailed solution and implementation plan. This remains part of Question 5 rather than a new lifecycle phase.

---

# 6. Complete pre-execution journal template

The following is the complete agreed template for the first record in a cycle.

The orchestrator renders the `Task to Solve` from the canonical task data. The model supplies the five accepted answers. Both are placed in the same journal document. The maintained standalone template is `cycle-intent-template.md`; the abbreviated shape below shows the same required ordering.

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
> model's project-context understanding, evidence, engineering synthesis,
> concrete candidates and decision.

## Task to Solve

### What is the task, and what must the final result satisfy?

<Exact canonical task block supplied to the model>

## Model Response

### 1. What engineering problem is currently established in the context of this project?

<Model answer>

### 2. What information was needed to develop an evidence-supported solution,
and what did the model find?

| Information needed | Why it was needed | Sources examined | Finding | What remains unknown or requires execution |
|---|---|---|---|---|
| <information> | <reason> | <actual sources or methods> | <finding> | <remaining gap> |

#### Material assumptions that remain necessary

<Model answer or None>

### 3. What project-applicable engineering synthesis and high-level solution space follow from the established evidence?

<Model answer deriving the project-applicable high-level approaches>

### 4. What concrete solutions translate the surviving high-level approaches into implementable changes?

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

### 5. Which solution is selected, and why is it preferred?

Before committing, challenge whether the leading candidate is merely workable or
is the strongest project-fit solution reasonably supported by the available
evidence. Investigate and reconsider only when a materially unresolved decision
issue and reasonably obtainable evidence could materially change selection. This
does not require exhaustive exploration, manufactured alternatives, or multiple
candidates; one candidate remains valid after evidence-based elimination.

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
- All five Model Response questions are required.
- Question 2 must identify actual evidence sources or investigation methods.
- Question 3 is a proportional engineering-synthesis and high-level solution-space artifact, not an implementation plan or deterministic semantic score.
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
- routes initial engineering capabilities to an isolated cycle experiment;
- requires a pre-execution submission;
- unlocks material capabilities after accepted submission;
- renders the accepted data into `decision-journal.md`.

Implementation of this design should therefore replace and restructure the current Cycle Intent content without replacing the existing workflow sequence.

This document intentionally stops at acceptance of the pre-execution analysis and solution decision. The later implementation/reassessment record, post-execution questionnaire, deterministic-validation presentation and next-cycle prompt are outside its current scope.
