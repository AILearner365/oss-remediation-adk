# Autonomous Agent — Project Direction

**Updated:** 2026-09-27. **Scope:** development-project continuity for `autonomous_oss_remediation_agent` on `context-hygiene-clone-challenge-before-commitment`. These files are for ChatGPT/developers; they are not agent runtime inputs. See [WORK-STATE](WORK-STATE.md) for the active bookmark and [DECISION-LOG](DECISION-LOG.md) for durable rationale.

## Objective and direction

The project began as automated Critical/High OSS vulnerability remediation for a multi-module Java/Spring Boot Maven repository. The current direction is a **general autonomous engineering problem-solving model**, first proven through OSS remediation: deterministic preparation/baseline, one reasoning/coding agent, independent deterministic validation, evidence-informed N+1 recovery, then gated delivery. The agent should reason about actual ownership/control points, compatibility, alternatives and evidence rather than follow scanner-to-version recipes. The test target remains `AILearner365/maven-multimodule-app`.

The active implementation is `autonomous_oss_remediation_agent`. Older `oss_remediation_agent` and `docs/phase-*` material is historical. Runtime authority remains the active package implementation and journal/prompt contracts. [Experiment 1](../EXPERIMENT_1_CHALLENGE_BEFORE_COMMITMENT.md) governs the frozen hypothesis/evaluation protocol, not runtime architecture. A separately discussed `autonomous-problem-solving-operating-model.md` is still not present on this branch.

## Journey and work map

| ID | Stage / workstream | Status | Evidence and next boundary |
|---|---|---|---|
| S1 | OSS workflow discovery and early ADK prototypes | Completed historical foundation | Project moved from multi-agent/exact-patch workflow to one autonomous engineering actor. |
| S2 | Independent autonomous POC and deterministic envelope | Implemented; hardening active | CLI/request, one ADK model/session, engineering tools, scanners, policy validation, cycles, journal and gated Draft PR delivery. |
| S3 | Evidence-grounded decision quality | Active | Q1–Q5 implemented. P1 studies premature commitment/project-fit selection. P1.1 Challenge Before Commitment remains frozen and under evaluation. |
| S4 | Runtime evidence, tool contract and recovery quality | Active supporting work | P2 bounded/recoverable evidence architecture is implemented. Latest audit localized tool-contract, runtime-resource acceptance and Intent-capture issues that must be cleaned before clean P1.1 comparison. P3 remains open. |
| S5 | Deployment and broader generalization | Upcoming / conditional | Repeatable evaluation, runner/credential isolation, provider reliability, portability and later deployment integration remain. |

## Meaningful backlog

| ID | Parent | Status | Work and dependency / return |
|---|---|---|---|
| P1 | S3 | Active | Improve consistency of project-fit solution selection without prescribing a dependency layer or candidate count. |
| P1.1 | P1 | Active; frozen behavior | Evaluate Challenge Before Commitment using clean comparable runs; task success and engineering decision quality are separate. Current decision: `CONTINUE`. |
| P1.1a | P1.1 | Completed | Durable project-continuity documents. |
| P1.1b | P1.1 + P2 | **Audit sufficiently complete; cleanup/acceptance next** | Six-run audit separated genuine reasoning variance from harness/runtime/capture contamination. Next sequence is Steps 2–4 in WORK-STATE, then return to clean P1.1 runs. |
| P2.1 | P2 | Implemented; test verification complete | Text edit now exposes write/replace only; `delete_workspace_file` explicitly removes an entire file. |
| P2.2 | P2 | Harness handoff tested; model acceptance next | A command-created current-cycle resource reaches an experimental scanner consumer; clean model-backed Maven → scanner → Intent evidence is still needed. |
| P2.3 | P2 | Implemented; test verification complete | Structural rejection feedback includes focused repair instructions; four identical Intent error sets stop orchestrator retries. Substantive validation remains unchanged. |
| P2 | S4 | Implemented architecture; behavioral acceptance incomplete | Bounded model-facing outputs + full retained evidence + targeted retrieval + experimental runtime resources. Do not overclaim paths not exercised in clean traces. |
| P3 | S4 | Backlog | Evidence-backed N+1 recovery and first meaningful failure localization; avoid failed-strategy momentum and distinguish strategy vs environment/harness/validation failure. |
| P4 | S3/S4 | Backlog / observed concern | Research/source recovery, stale-prior substitution and decision-critical investigation depth. Recent traces continue to show #18/#22/#25 behavior. |
| P5 | S5 | Deferred | Runner security, credentials, deployment and ADK Web/Agent Engine adaptation. |
| P6 | P1 | Conditional, not approved | Independent critique or broader branching/search only if clean Experiment 1 evidence justifies complexity. |

**Current position:** S3 with S4 cleanup supporting it. P2.1 and P2.3 fixes are implemented; P2.2 has deterministic handoff coverage. The next gate is targeted model-backed runtime-resource acceptance, followed by frozen repeated P1.1 runs if that path is clean. Do not modify Q1–Q5 while cleaning these independent defects.

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
- Freeze Experiment 1 while P2.1–P2.3 are fixed/verified so later causal evaluation remains interpretable.

## Current experimental conclusion

Recent evidence supports continuing Experiment 1 but does **not** support promotion. Q5 wording identifies the right search-sufficiency concern, yet multiple runs still allowed stale/unsupported priors about Spring Boot `4.0.6` to influence elimination/selection. Because recent final failures are contaminated by tool/runtime/capture defects, do not refine or advance the reasoning mechanism until clean comparable runs are available.

## Maintenance

ChatGPT owns project-level continuity bookkeeping during the ChatGPT → Codex implementation → GitHub review → Cloud Shell run → evidence-analysis loop. Update this direction, [WORK-STATE](WORK-STATE.md), and [DECISION-LOG](DECISION-LOG.md) when a meaningful problem, parent/child relation, return point, durable discovery, implementation result or runtime finding changes. Preserve observed evidence separately from interpretation. This folder must never become agent runtime context.
