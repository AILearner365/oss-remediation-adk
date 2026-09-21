# Post-Execution Prompt and Cycle Outcome Design

## Scope

This document defines the mandatory post-execution Cycle Outcome produced after the autonomous model has completed implementation and self-validation for a cycle.

It is the post-execution companion to `PRE_EXECUTION_PROMPT_AND_DECISION_JOURNAL_DESIGN.md`.

This design does not change the existing workflow sequence or independent deterministic validation. It defines:

1. the request sent to the model after execution has ended;
2. the mandatory Cycle Outcome questionnaire;
3. the rules for completing the questionnaire.

The Cycle Outcome is retrospective. It records what actually occurred during implementation and self-validation. It is not a new problem-analysis or solution-planning stage, and it does not establish deterministic success.

The existing control flow remains:

```text
Problem Analysis and Solution Decision / Cycle Intent
        ↓
Implementation and investigation
        ↓
Material reassessment when execution evidence requires it
        ↓
Self-validation
        ↓
Execution ends
        ↓
Post-execution Cycle Outcome request
        ↓
Submit Cycle Outcome
        ↓
Independent deterministic validation
```

---

# 1. Post-execution request

Execution has already ended when this request is sent. Repository read, edit, and shell capabilities are unavailable. The model must submit a metadata-only Cycle Outcome for every execution state, including successful, partial, blocked, failed, inconclusive, and no-change execution.

The request remains structurally the existing `outcome_message()` request, with terminology aligned to the Cycle Outcome questionnaire:

```python
def outcome_message(cycle: int, execution_summary: str, evidence: dict) -> str:
    return (
        f"Execution for Cycle {cycle} has ended. Repository read, edit, and shell capabilities are now unavailable. "
        "Submit a metadata-only Cycle Outcome through `submit_cycle_outcome` for any successful, partial, blocked, "
        "failed, inconclusive, or no-change execution. Report what was actually implemented, any material differences "
        "from the selected solution, material implementation evidence and reassessments, self-validation, and unresolved "
        "coverage. Scope each self-validation claim to what its underlying check actually evaluated; keep unevaluated "
        "coverage unresolved or unverified, and do not claim deterministic success.\n\n"
        + outcome_questionnaire()
        + "\n\nExecution response (compatibility evidence):\n"
        + execution_summary
        + "\n\nDeterministic execution evidence available before validation:\n"
        + json.dumps(evidence, indent=2, sort_keys=True, default=str)
    )
```

The detailed answer requirements belong to `outcome_questionnaire()` rather than expanding this wrapper.

---

# 2. Cycle Outcome questionnaire

The model must answer the following three questions.

## 1. Implementation Result

### Question supplied to the model

```markdown
### 1. Implementation Result

What was actually implemented during this cycle, and what did your self-validation establish against the Task to Solve, including its success criteria and constraints?

If no solution or only a partial solution was implemented, state that explicitly and identify what remains unresolved or unverified.
```

## 2. Cycle Intent vs. Implementation

### Question supplied to the model

```markdown
### 2. Cycle Intent vs. Implementation

Did the implemented solution materially differ from the selected strategy recorded in the Cycle Intent? If yes, what changed, what evidence or findings discovered during implementation led to the material reassessment, and why was the resulting strategy or solution selected?

If there was no material change from the Cycle Intent, state that directly.
```

## 3. Implementation Trail

### Question supplied to the model

```markdown
### 3. Implementation Trail

What was the actual sequence of material implementation and investigation actions from the Cycle Intent through self-validation?
```

---

# 3. Rules for completing the Cycle Outcome

The following rules apply to all three answers:

- Report only what actually occurred during this cycle. Do not infer, reconstruct, or invent implementation actions, investigation, evidence, findings, alternatives, reassessments, decisions, or self-validation that did not occur.
- Base statements on the model's actual execution experience and the evidence available from the cycle. Clearly distinguish observed facts, self-validation results, unresolved uncertainty, and unverified expectations.
- Keep the answers consistent with the Task to Solve and the Cycle Intent. Do not rewrite, narrow, expand, or reinterpret either of them retrospectively.
- Focus on material information. Do not produce a command-by-command diary or report routine edits, retries, navigation, or tool usage unless they materially affected the implementation or a decision.
- When implementation produced evidence that materially changed the selected strategy, record the evidence or finding, what it changed about the previous understanding or strategy, and the resulting change in direction.
- Do not manufacture a material reassessment merely because the final implementation differs from the Cycle Intent. Report a reassessment only if one actually occurred during execution.
- When referring to evidence, identify the actual evidence or observed result sufficiently to support the statement. Do not claim something was established when it was only assumed or expected.
- Report failed or unsuccessful implementation attempts when they materially influenced the resulting implementation, eliminated an approach, disproved an assumption, or left part of the Task to Solve unresolved.
- Report the self-validation actually performed and its actual results. Scope each claim to the properties the underlying check actually evaluated. A successful check does not establish a requirement, success criterion, constraint, or outcome it did not evaluate; keep that coverage unresolved or unverified. Do not claim validation that was not performed.
- Self-validation does not establish authoritative success. Do not claim that the Task to Solve is deterministically resolved merely because the model's own checks passed.
- For applicable success criteria and constraints, clearly identify what the cycle's implementation and self-validation indicate is satisfied, not satisfied, unresolved, or unverified.
- If implementation was partial, blocked, failed, inconclusive, or resulted in no change, report that state directly rather than forcing the response to describe a successful solution.
- Do not expose hidden chain-of-thought. Provide only concise, decision-relevant facts, evidence, conclusions, and rationale necessary to explain what happened.
- Avoid unnecessary repetition across the three answers:
  - Question 1 describes the resulting implementation and self-validation state.
  - Question 2 explains material deviation from the Cycle Intent, if any.
  - Question 3 provides the chronological material implementation and investigation trail.

---

# 4. Information separation across the three questions

The three questions intentionally serve different purposes.

**Implementation Result** records where implementation ended and what self-validation established against the Task to Solve.

**Cycle Intent vs. Implementation** records whether execution materially departed from the selected strategy and, when it did, the implementation evidence and material reassessment that led to the resulting strategy or solution.

**Implementation Trail** records the actual chronological path through material implementation and investigation actions, observed results, material reassessments when they occurred, and self-validation.

Together they provide the minimum post-execution record needed to understand what was implemented, how it related to the Cycle Intent, and how execution actually reached that state without turning the Cycle Outcome into a command log or a second planning exercise.

---

# 5. Boundary with deterministic validation

The Cycle Outcome records the model's implementation experience and self-validation. It does not determine authoritative success.

Independent deterministic validation occurs after the Cycle Outcome and remains authoritative.

The separation is:

```text
Cycle Intent
    = what the model selected before implementation

Implementation
    = what the model actually did and adapted during execution

Cycle Outcome
    = retrospective record of implementation, material reassessment,
      self-validation, and unresolved coverage

Independent Deterministic Validation
    = authoritative objective evaluation of the resulting state
```

The model must therefore report its self-validation accurately without converting those results into a claim of deterministic success.
