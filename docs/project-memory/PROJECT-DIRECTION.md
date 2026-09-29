# Autonomous Agent — Project Direction

**Updated:** 2026-09-29. **Scope:** development-project continuity for `autonomous_oss_remediation_agent` on `context-hygiene-clone-challenge-before-commitment`. These files are for ChatGPT/developers; they are not agent runtime inputs. See [WORK-STATE](WORK-STATE.md) for the active bookmark and [DECISION-LOG](DECISION-LOG.md) for durable rationale.

## Objective and direction

The project began as automated Critical/High OSS vulnerability remediation for a multi-module Java/Spring Boot Maven repository. The current direction is a **general autonomous engineering problem-solving model**, first proven through OSS remediation: deterministic preparation/baseline, one reasoning/coding agent, independent deterministic validation, evidence-informed N+1 recovery, then gated delivery. The agent should reason about actual ownership/control points, compatibility, alternatives and evidence rather than follow scanner-to-version recipes. The test target remains `AILearner365/maven-multimodule-app`.

The active implementation is `autonomous_oss_remediation_agent`. Older `oss_remediation_agent` and `docs/phase-*` material is historical. Runtime authority remains the active package implementation and journal/prompt contracts. [Experiment 1](../EXPERIMENT_1_CHALLENGE_BEFORE_COMMITMENT.md) governs the frozen hypothesis/evaluation protocol, not runtime architecture. A separately discussed `autonomous-problem-solving-operating-model.md` is still not present on this branch.

## Journey and work map

| ID | Stage / workstream | Status | Evidence and next boundary |
|---|---|---|---|
| S1 | OSS workflow discovery and early ADK prototypes | Completed historical foundation | Project moved from multi-agent/exact-patch workflow to one autonomous engineering actor. |
| S2 | Independent autonomous POC and deterministic envelope | Implemented; hardening active | CLI/request, one ADK model/session, engineering tools, scanners, policy validation, cycles, journal and gated Draft PR delivery. |
| S3 | Evidence-grounded decision quality | Active | Q1–Q5 implemented. P1 studies premature commitment/project-fit selection. P1.1 Challenge Before Commitment remains frozen and under evaluation. |
| S4 | Runtime evidence, tool contract and recovery quality | Active supporting work | The P2.3 capture-contract defect in `011744` is fixed and tested: ADK exposed arbitrary answer dictionaries, while the journal required `answer` and the model repeatedly sent `content`. P2.2 handoff remains separate. Retained-evidence retrieval under truncation is the next live acceptance question. |
| S5 | Deployment and broader generalization | Upcoming / conditional | Repeatable evaluation, runner/credential isolation, provider reliability, portability and later deployment integration remain. |

## Meaningful backlog

| ID | Parent | Status | Work and dependency / return |
|---|---|---|---|
| P1 | S3 | Active | Improve consistency of project-fit solution selection without prescribing a dependency layer or candidate count. |
| P1.1 | P1 | Active; frozen behavior | Evaluate Challenge Before Commitment using clean comparable runs; task success and engineering decision quality are separate. Current decision: `CONTINUE`. |
| P1.1a | P1.1 | Completed | Durable project-continuity documents. |
| P1.1b | P1.1 + P2 | Evaluation paused for capture cleanup | Historical audit separated reasoning defects from harness contamination. `011744` ended without accepted Intent because of a field-name contract mismatch; do not score that outcome as reasoning-strategy evidence. |
| P2.1 | P2 | Resolved for now | Text edit exposes write/replace only; `delete_workspace_file` explicitly removes an entire file. Latest successful runs did not reproduce the accidental file-unlink failure. |
| P2.2 | P2 | Capability covered; optional live path unobserved | Current-cycle runtime-resource handoff is implemented and tested. The exact model-backed Maven/resource → experimental scanner → Intent path remains unproven. Its non-use is not a P1.1 evaluation gate; investigate a failed attempt's cause separately or test the path when a decision depends on its availability. |
| P2.3 | P2 | Capture-contract fix implemented and tested; live recovery unobserved | The ten `011744` Intent calls used `section`/`content`; journal validation required `section`/`answer` and feedback did not identify the key mismatch. The tool schema now requires both fields and rejection explicitly identifies missing `answer`, preserving substantive validation. |
| P2.4 | P2 | Next separate live acceptance | Two 3,000-character runs had truncated shell output retained with references and file-read continuation, but neither called `retrieve_retained_evidence`. Test truncation → retrieval → use of the retrieved fact separately after P2.3 is clean. |
| P2 | S4 | Implemented architecture; some live paths unobserved | Bounded model-facing outputs + full retained evidence + targeted retrieval + experimental runtime resources. Do not overclaim paths not exercised in clean traces or make optional evidence methods mandatory for P1.1. |
| P3 | S4 | Backlog | Evidence-backed N+1 recovery and first meaningful failure localization; avoid failed-strategy momentum and distinguish strategy vs environment/harness/validation failure. |
| P4 | S3/S4 | Active observed concern | Stale-prior substitution and decision-critical investigation depth remain visible. Recent runs vary: some still call Spring Boot `4.0.6` custom/non-public; another treats it as intentional/custom and preserves it, but without first establishing the parent control point from authoritative evidence. |
| P5 | S5 | Deferred | Runner security, credentials, deployment and ADK Web/Agent Engine adaptation. |
| P6 | P1 | Conditional, not approved | Independent critique or broader branching/search only if clean Experiment 1 evidence justifies complexity. |

**Current position:** S4/P2.3 capture-contract fix has focused and broader test coverage but no new live recovery trace. Next run the separate P2.4 live retained-evidence exercise, then return to comparable frozen P1.1 runs. P2.2 experimental scanner handoff remains an independent unobserved path, not a required scanner-use gate. Do not change Q1–Q5 meanwhile.

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

Recent post-fix runs improve confidence in end-to-end execution but do not settle Experiment 1. Two newest runs (`20260928T014926Z`, `20260928T015654Z`) both passed deterministic validation and delivered Draft PRs (#195, #196), yet neither performed an experimental scanner call before Intent. Reasoning variance also remains: stale/unsupported assumptions about Spring Boot `4.0.6` still influence some traces. Experiment 1 therefore remains `CONTINUE`, not `PROMOTE`.

## Maintenance

ChatGPT owns project-level continuity bookkeeping during the ChatGPT → Codex implementation → GitHub review → Cloud Shell run → evidence-analysis loop. Update this direction, [WORK-STATE](WORK-STATE.md), and [DECISION-LOG](DECISION-LOG.md) when a meaningful problem, parent/child relation, return point, durable discovery, implementation result or runtime finding changes. Preserve observed evidence separately from interpretation. This folder must never become agent runtime context.
