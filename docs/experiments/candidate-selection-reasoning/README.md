# Candidate-Selection Reasoning feasibility experiment

Status: **design only**. No agent implementation or reasoning run has been
performed. Baseline: `73bb7e3ad960571fccd938cf5499464a8441c71f` on
`spring-boot-release-intelligence-feasibility`.

## Question

Can one autonomous reasoning agent discover, compare, select, and revise a
credible Spring Boot/Maven remediation strategy from evidence, without receiving
a candidate shortlist or a vulnerability-specific recipe?

This is not a production remediator. It evaluates bounded decision behavior.
Existing A2 + narrow A1 + OSV components are evidence infrastructure; Maven and
the independent validator—not the model—establish effective dependencies,
vulnerability outcomes, and build/test results.

## Experimental unit

One unchanged agent configuration is run independently on each task. The agent
receives only the task goal, constraints, baseline project/findings, generic
tool descriptions, and its own prior trace. It does **not** receive hidden
expectations, a release shortlist, a preferred strategy type, vulnerability
fix versions, or the outcome of candidates it has not investigated.

Each run has two stages:

1. **Discovery and selection:** inspect the project, discover eligible releases
   and controls, gather evidence, compare at least the candidates it considers
   credible, and submit one exact proposed Maven change plus a structured
   decision record.
2. **Independent validation and revision:** a deterministic harness applies the
   exact proposal in a disposable copy, resolves Maven dependencies, evaluates
   original/new findings, and runs configured build/tests. Only the resulting
   evidence is returned. The same agent may retain, revise, or withdraw its
   strategy, with reasons.

Maximum bounds per task: 20 evidence-tool calls, 3 validation submissions
(initial plus two revisions), 15 minutes wall time, 200 MB new evidence, and no
network destination beyond configured Maven repositories, OSV, and optional
deps.dev. Tool-call and token usage are recorded, not used as quality proxies.

## Non-goals

- Implementing a rigid candidate ranker or fixed upgrade recipes.
- Editing production applications or the OpenHands workspace.
- Treating build success, finding counts, newest release, or an empty OSV result
  as sufficient evidence of a good decision.
- Measuring model chain-of-thought. Only observable claims, actions, tool calls,
  decision records, and revisions are captured.

See [live-test-cases.md](live-test-cases.md),
[evidence-requirements.md](evidence-requirements.md),
[evaluation-criteria.md](evaluation-criteria.md), and
[execution-plan.md](execution-plan.md).
