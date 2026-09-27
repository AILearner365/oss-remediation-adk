# Autonomous Agent — Project Direction

**Updated:** 2026-09-27. **Scope:** development-project continuity for `autonomous_oss_remediation_agent` on `context-hygiene-clone-challenge-before-commitment`. These files are for ChatGPT/developers; they are not inputs to the agent runtime. See [WORK-STATE](WORK-STATE.md) for the current bookmark and [DECISION-LOG](DECISION-LOG.md) for rationale.

## Objective and direction

The project began as automated Critical/High OSS vulnerability remediation for a multi-module Java/Spring Boot Maven repository: assess findings, make constrained dependency changes, rebuild and rescan, and offer a human-reviewed PR. The current direction is a **general autonomous engineering problem-solving model**, proven first through OSS remediation: deterministic preparation/baseline, one reasoning and coding agent, independent deterministic validation, evidence-informed recovery across cycles, then gated delivery. The agent should reason about ownership, compatibility, alternatives and evidence instead of following scanner-to-version recipes. The test target remains `AILearner365/maven-multimodule-app`.

The active implementation is the independent `autonomous_oss_remediation_agent` package. The older `oss_remediation_agent` and `docs/phase-*` specifications are historical. Runtime authority remains the package README, pre-execution journal design, post-execution journal design and implementation. [Experiment 1](../EXPERIMENT_1_CHALLENGE_BEFORE_COMMITMENT.md) governs its frozen hypothesis/evaluation, not runtime behavior. A separately discussed `autonomous-problem-solving-operating-model.md` is not present on this branch; locate and reconcile its authoritative copy before citing exact text.

## Journey and work map

| ID | Stage / workstream | Status | Evidence and next boundary |
|---|---|---|---|
| S1 | OSS workflow discovery and early ADK prototypes | Completed as historical foundation | Earlier multi-agent discovery/planning/patch/PR workflow remains historical; project moved to one autonomous actor. |
| S2 | Independent autonomous POC and deterministic envelope | Implemented; operational hardening continues | CLI/request, one ADK model/session, engineering tools, scanners, policy validation, cycles, journal and gated Draft PR delivery. |
| S3 | Evidence-grounded decision quality | Active | Q1–Q5 implemented. P1 studies premature commitment/project-fit solution quality. P1.1 Challenge Before Commitment is frozen for evaluation. |
| S4 | Runtime evidence and recovery quality | Active supporting work | P2 bounded/recoverable evidence changes are implemented, but the latest conversation exposed an unresolved evidence-audit boundary before recent runs can be cleanly interpreted. P3 recovery remains open. |
| S5 | Deployment and broader generalization | Upcoming / conditional | Repeatable comparison, runner/credential isolation, provider/environment reliability, portability and later deployment integration remain. |

## Meaningful backlog

| ID | Parent | Status | Work and dependency / return |
|---|---|---|---|
| P1 | S3 | Active | Improve consistency of project-fit solution selection without prescribing a dependency layer or forcing candidate counts. |
| P1.1 | P1 | Active, temporarily blocked on evidence classification | Evaluate frozen Challenge Before Commitment using genuinely comparable runs; separate task success from decision quality. |
| P1.1a | P1.1 | Completed | Durable project-continuity documents. |
| P1.1b | P1.1 + P2 | **Active temporary child** | Finish full evidence timeline for problematic recent runs. Determine why the model-side experimental scanner loop was absent/not successfully recorded before Intent and whether failures are reasoning, invocation, runtime-resource, capability, context/tool-pressure, validation, or other harness causes. **Return to P1.1 immediately after classification/fix/exclusion.** |
| P2 | S4 | Implemented architecture; behavioral acceptance incomplete | Bounded model-facing outputs + full retained evidence + targeted retrieval; scanner consistency; experimental runtime resources. Do not overclaim model-backed coverage for paths not exercised in traces. |
| P3 | S4 | Backlog | Evidence-backed N+1 recovery, first meaningful failure localization, transitive/BOM/parent/framework compatibility; avoid strategy momentum. |
| P4 | S3/S4 | Backlog | Research/source discovery reliability, unsupported-prior substitution and decision-critical investigation depth. |
| P5 | S5 | Deferred | Runner security, credentials, deployment and ADK Web/Agent Engine adaptation. |
| P6 | P1 | Conditional, not approved | Independent critique or broader branching/search only if experiment evidence justifies complexity. |

**Current position:** S3 with S4 supporting. P1.1 remains the parent experiment, but **P1.1b is the immediate active work** because recent runs are not yet clean evidence for or against Challenge Before Commitment. Complete the evidence audit first; resolve/fix or exclude contaminated runs; then return to P1.1 repeat-run evaluation. Do not infer decision quality from a passing build/PR, and do not infer context/scanner failure from a path that the model did not actually exercise.

## Stable reasoning/evidence boundaries

- Hard constraints are candidate-admissibility gates.
- One candidate is legitimate when evidence genuinely eliminates other approaches; candidate count is not the target.
- Evidence outranks unsupported prior expectations; failed retrieval preserves uncertainty.
- The target is not a provable global optimum but the strongest project-fit solution reasonably supported after sufficient investigation.
- Context/evidence handling is **bounded + recoverable**: full raw evidence is retained; the model receives compact semantic results/references and can retrieve details.
- A deterministic validation result must be interpreted within the validity of its observed environment/state; environment or dependency-state mismatch is not automatically strategy failure.
- Avoid prompt accumulation and case-specific Maven/Spring recipes. Refine generic invariants only after evidence identifies a reasoning defect.

## Maintenance

ChatGPT owns project-level continuity bookkeeping during the ChatGPT → Codex implementation → GitHub review → Cloud Shell run → evidence analysis loop. Update this direction, [WORK-STATE](WORK-STATE.md), and [DECISION-LOG](DECISION-LOG.md) when a meaningful problem, parent/child relation, return point, stage, backlog item, material decision, implementation result or runtime finding changes. Preserve observed evidence separately from interpretation. No runtime prompt, Task to Solve, Cycle Intent/Outcome, orchestration, validation, model context or configuration consumes this folder.
