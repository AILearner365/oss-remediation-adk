# Autonomous Agent — Project Direction

**Updated:** 2026-10-02. **Scope:** development-project continuity for `autonomous_oss_remediation_agent` on `context-hygiene-clone-challenge-before-commitment`. These files are for ChatGPT/developers; they are not agent runtime inputs. See [WORK-STATE](WORK-STATE.md) for the active bookmark and [DECISION-LOG](DECISION-LOG.md) for durable rationale.

## Objective and direction

The project began as automated Critical/High OSS vulnerability remediation for a multi-module Java/Spring Boot Maven repository. The current direction is a **general autonomous engineering problem-solving model**, first proven through OSS remediation: deterministic preparation/baseline, one reasoning/coding agent, independent deterministic validation, evidence-informed N+1 recovery, then gated delivery. The agent should reason about actual ownership/control points, compatibility, alternatives and evidence rather than follow scanner-to-version recipes. The test target remains `AILearner365/maven-multimodule-app`.

The active implementation is `autonomous_oss_remediation_agent`. Older `oss_remediation_agent` and `docs/phase-*` material is historical. Runtime authority remains the active package implementation and journal/prompt contracts. [Experiment 1](../EXPERIMENT_1_CHALLENGE_BEFORE_COMMITMENT.md) governs the frozen hypothesis/evaluation protocol, not runtime architecture. A separately discussed `autonomous-problem-solving-operating-model.md` is still not present on this branch.

## Journey and work map

| ID | Stage / workstream | Status | Evidence and next boundary |
|---|---|---|---|
| S1 | OSS workflow discovery and early ADK prototypes | Completed historical foundation | Project moved from multi-agent/exact-patch workflow to one autonomous engineering actor. |
| S2 | Independent autonomous POC and deterministic envelope | Implemented; hardening active | CLI/request, one ADK model/session, engineering tools, scanners, policy validation, cycles, journal and gated Draft PR delivery. |
| S3 | Evidence-grounded decision quality | Active | Q1–Q5 implemented. P1 studies premature commitment/project-fit selection. P1.1 Challenge Before Commitment remains frozen and under evaluation. |
| S4 | Runtime evidence, tool contract and recovery quality | Active supporting work | October 2 runs establish specific same-cycle recovery, retained retrieval, and experimental scanner paths. Focused research acquisition, Outcome grounding and scanner-transition guidance follow-up is implemented; new live acceptance remains. |
| S5 | Deployment and broader generalization | Upcoming / conditional | Repeatable evaluation, runner/credential isolation, provider reliability, portability and later deployment integration remain. |

## Meaningful backlog

| ID | Parent | Status | Work and dependency / return |
|---|---|---|---|
| P1 | S3 | Active | Improve consistency of project-fit solution selection without prescribing a dependency layer or candidate count. |
| P1.1 | P1 | Active; frozen behavior | Evaluate Challenge Before Commitment using clean comparable runs; task success and engineering decision quality are separate. Current decision: `CONTINUE`. |
| P1.1a | P1.1 | Completed | Durable project-continuity documents. |
| P1.1b | P1.1 + P2 | Evaluation paused for capture cleanup | Historical audit separated reasoning defects from harness contamination. `011744` had the now-fixed answer-field mismatch; `022558` lost Intent cycles after unregistered ADK tool calls. Neither capture failure is clean P1.1 strategy evidence. |
| P2.1 | P2 | Focused read/edit protection implemented; live acceptance pending | A later run reconstructed an existing file from an incomplete read and lost an unrelated trailing profile. Existing-file whole writes now require complete current-content read coverage; targeted replace preserves the tail. Shell edits remain outside this tool contract. |
| P2.2 | P2 | Experimental handoff live-observed; transition repair pending live | `011600` used a HOME-based resource for an experimental scan (8 findings, then clean) before Intent. Authoritative calls wrongly retained the experimental-only argument; focused error guidance now identifies the supported retry without it. |
| P2.3 | P2 | Same-session recovery live-observed; boundary tested offline | `011600` recovered from three unknown calls and accepted Intent on shared attempt 4 in one session/cycle. The tenth-attempt success/exhaustion boundary remains offline-tested only. |
| P2.4 | P2 | Retained retrieval live-observed with limited causal claim | `005510` retrieved two bounded-output ranges successfully, then obtained the decisive Jackson fact through a filtered shell command. Do not credit retrieval alone with the correction. Outcome now also exposes retained final-state/check evidence; its live use remains to verify. |
| P2 | S4 | Implemented architecture; some live paths unobserved | Bounded model-facing outputs + full retained evidence + targeted retrieval + experimental runtime resources. Do not overclaim paths not exercised in clean traces or make optional evidence methods mandatory for P1.1. |
| P3 | S4 | Backlog | Evidence-backed N+1 recovery and first meaningful failure localization; avoid failed-strategy momentum and distinguish strategy vs environment/harness/validation failure. |
| P4 | S3/S4 | Active observed concern | Stale-prior substitution and decision-critical investigation depth remain visible. Recent runs vary: some still call Spring Boot `4.0.6` custom/non-public; another treats it as intentional/custom and preserves it, but without first establishing the parent control point from authoritative evidence. |
| P5 | S5 | Deferred | Runner security, credentials, deployment and ADK Web/Agent Engine adaptation. |
| P6 | P1 | Conditional, not approved | Independent critique or broader branching/search only if clean Experiment 1 evidence justifies complexity. |

**Current position:** S4/P2 evidence work reconciled the reviewed baseline `38263075` with the branch head. A focused Outcome-summary correction counts additions/removals inside unified hunks, accounts for both character and line clipping at retained/model-facing levels, and labels unsupported or malformed diffs explicitly. File-list completeness remains separate from excerpt completeness. The existing read receipts, capture recovery and Final Resolution reconciliation remain in place. Next check a bounded summary followed by retained-diff retrieval in a small live exercise, then return to comparable frozen P1.1 evaluation at CONTINUE. See WORK-STATE for exact evidence and limits.

## Stable reasoning/evidence boundaries

- Hard constraints are candidate-admissibility gates.
- One candidate is legitimate when evidence genuinely eliminates other approaches; candidate count is not the target.
- Evidence outranks unsupported prior expectations; failed retrieval preserves uncertainty.
- The target is the strongest project-fit solution reasonably supported after sufficient investigation, not a proof of global optimum.
- Context/evidence handling is **bounded + recoverable**.
- Tool/runtime/capture defects must be separated from engineering-strategy defects.
- Deterministic validation is authoritative only for what its observed environment/state validly establishes.
- Same-cycle reassessment remains allowed and valuable.
- Avoid prompt accumulation and case-specific Maven/Spring recipes.
- Successful delivery does not prove pre-Intent investigation quality or P2.2 acceptance.
- A successful experimental scanner call is one possible evidence path, not a required step in the frozen P1.1 protocol. Evaluate whether the model obtained sufficient decision-relevant evidence through the paths it actually used.

## Current experimental conclusion

The prior one-cycle successes from target `9ea1b0ed5ca255db0fc7c659d050896d3ed5db78` resolved 24/24 findings and delivered Draft PRs #199-201, but did not establish consistent decision quality. The next batch at `1dd959f4` exposed a different destructive file reconstruction despite passing build/OSV validation and PR #203 delivery, and a three-cycle run whose final validation passed after a stale partial Outcome. Passing delivery or validation does not validate earlier reasoning or unrelated file preservation. Experiment 1 remains **CONTINUE**.

## Maintenance

ChatGPT owns project-level continuity bookkeeping during the ChatGPT → Codex implementation → GitHub review → Cloud Shell run → evidence-analysis loop. Update this direction, [WORK-STATE](WORK-STATE.md), and [DECISION-LOG](DECISION-LOG.md) when a meaningful problem, parent/child relation, return point, durable discovery, implementation result or runtime finding changes. Preserve observed evidence separately from interpretation. This folder must never become agent runtime context.
