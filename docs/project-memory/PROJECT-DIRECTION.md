# Autonomous Agent — Project Direction

**Updated:** 2026-09-27. **Scope:** development-project continuity for `autonomous_oss_remediation_agent` on `context-hygiene-clone-challenge-before-commitment`. These files are for ChatGPT/developers; they are not inputs to the agent runtime. See [WORK-STATE](WORK-STATE.md) for the current bookmark and [DECISION-LOG](DECISION-LOG.md) for rationale.

## Objective and direction

The project began as automated Critical/High OSS vulnerability remediation for a multi-module Java/Spring Boot Maven repository: assess findings, make constrained dependency changes, rebuild and rescan, and offer a human-reviewed PR. The current direction is a **general autonomous engineering problem-solving model**, proven first through OSS remediation: deterministic preparation/baseline, one reasoning and coding agent, independent deterministic validation, evidence-informed recovery across cycles, then gated delivery. The agent should reason about ownership, compatibility, alternatives and evidence instead of following scanner-to-version recipes. The test target remains [`AILearner365/maven-multimodule-app`](https://github.com/AILearner365/maven-multimodule-app).

The active implementation is the independent `autonomous_oss_remediation_agent` package in this repository. The older `oss_remediation_agent` and the `docs/phase-*` multi-agent/patch-plan specifications describe an earlier workstream; they do not override the current autonomous package. The current runtime contract lives in [the package README](../../autonomous_oss_remediation_agent/README.md), [pre-execution design](../problem-solving-journal/PRE_EXECUTION_PROMPT_AND_DECISION_JOURNAL_DESIGN.md), [post-execution design](../problem-solving-journal/POST_EXECUTION_PROMPT_AND_CYCLE_OUTCOME_DESIGN.md), and the implementation itself. [Experiment 1](../EXPERIMENT_1_CHALLENGE_BEFORE_COMMITMENT.md) governs its frozen hypothesis and evaluation, not runtime behavior. A separately discussed `autonomous-problem-solving-operating-model.md` is not present on this branch; locate and reconcile its current authoritative copy before citing its exact text.

## Journey and work map

Status means project progress, not a claim that every deployment or experiment is complete. IDs are stable bookmarks; child and return relationships are in [WORK-STATE](WORK-STATE.md).

| ID | Stage / workstream | Status | Evidence and next boundary |
|---|---|---|---|
| S1 | OSS workflow discovery and early ADK prototypes | Completed as historical foundation | Earlier multi-agent discovery/planning/patch/PR workflow and `docs/phase-*` specifications remain in the repo. The project moved to a single autonomous actor after concerns about hand-crafted decisions and solution quality. |
| S2 | Independent autonomous POC and deterministic envelope | Implemented; operational hardening continues | `autonomous_oss_remediation_agent`: CLI/request, one ADK `LlmAgent` and continuing session, read/edit/shell, Maven and OSV/Xray, policy validation, cycles, journal and gated Draft PR delivery. See package README and code. |
| S3 | Evidence-grounded decision quality | Active | Q1–Q5 investigation, synthesis, candidates and selection are implemented. **P1** tests whether the agent commits to a workable approach too early; **P1.1** Experiment 1 is frozen and awaits assessed repeat runs. |
| S4 | Runtime evidence and recovery quality | Active supporting work | **P2** context/evidence hygiene fixes were implemented and unit/integration tested. Model-backed acceptance of those fixes, first-failure localization and dependency/BOM/framework recovery need evaluation. |
| S5 | Deployment and broader generalization | Upcoming / conditional | Repeatable comparison, runner/credential isolation, live integration, provider and environment reliability, portability beyond Maven, and later Agent Engine/ADK Web integration are not established by this POC. |

## Meaningful backlog

| ID | Parent | Status | Work and dependency / return |
|---|---|---|---|
| P1 | S3 | Active | Improve consistency of project-fit solution selection without prescribing a dependency layer or forcing candidate counts. |
| P1.1 | P1 | Evaluation pending | Run the frozen Challenge Before Commitment baseline repeatedly, inspect Q1–Q5/tool traces and outcomes, record costs and self-evaluation, decide CONTINUE/REFINE/REJECT/PROMOTE/ADVANCE. [Protocol](../EXPERIMENT_1_CHALLENGE_BEFORE_COMMITMENT.md). |
| P1.1a | P1.1 | Completed temporary child | Established project continuity in this folder. Return to P1.1 evaluation; this documentation task does not itself validate the hypothesis. |
| P2 | S4 | Implemented; model acceptance pending | Bounded model-facing outputs with retained evidence and continuation; scanner outcome consistency; experimental runtime resource handling. Recheck through real runs and resolve regressions if evidenced. |
| P3 | S4 | Backlog | Evidence-backed failed-cycle recovery, including first meaningful failure boundary and Maven transitive/BOM/parent/framework compatibility; avoid inheriting an invalid strategy. |
| P4 | S3/S4 | Backlog | Research/source discovery reliability, unsupported-prior substitution, and decision-critical investigation depth. Generic evidence-recovery wording exists; provider reliability remains separate. |
| P5 | S5 | Deferred | Runner security, credentials, deployment integration and ADK Web/Agent Engine adaptation after evidence and operational prerequisites. |
| P6 | P1 | Conditional, not approved | Independent critique or broader branching/search only if Experiment 1 evidence justifies the added complexity. |

**Current position:** S3, with S4 supporting fixes. P1.1a is complete; P1.1 is again the active focus. After repeated model-backed evaluation, use its recorded evidence to decide whether to refine or adopt the challenge, investigate P4/P3, or test another mechanism. Do not infer engineering decision quality from a passing build or PR alone.

## Maintenance

ChatGPT owns project-level continuity bookkeeping during the ChatGPT → Codex implementation → GitHub review → Cloud Shell run → evidence analysis loop. Update this direction, [WORK-STATE](WORK-STATE.md), and [DECISION-LOG](DECISION-LOG.md) when a meaningful problem, parent/child relation, return point, stage, backlog item, material decision, implementation result or runtime finding changes. Keep trivial messages and code details in their proper records. Preserve observed evidence separately from interpretation, reconcile conversation intent with the actual branch, and leave technical behavior to the authoritative sources above. No runtime prompt, Task to Solve, Cycle Intent/Outcome, questionnaire, orchestration, validation, model context or configuration consumes this folder.
