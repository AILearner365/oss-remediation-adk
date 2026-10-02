# Autonomous Agent — Project Direction

**Updated:** 2026-10-02. **Scope:** development-project continuity for `autonomous_oss_remediation_agent` on `context-hygiene-clone-challenge-before-commitment`. These files are for ChatGPT/developers; they are not agent runtime inputs. See [WORK-STATE](WORK-STATE.md) for the active bookmark and [DECISION-LOG](DECISION-LOG.md) for durable rationale.

## Objective and direction

**Latest S4/P2 boundary:** source head `acd6dee1` was reconciled with the pushed live fixture workspace at `667fff37`. That run autonomously recovered an omitted command fact but ended without Intent because the development fixture stopped after one turn. The fixture now continues within the production checkpoint bound and reports retrieval, capture, and selected-decision evidence separately. A small scenario catalogue distinguishes offline boundary checks from still-unverified autonomous Outcome/edit behavior. This is supporting evidence work; the return point remains comparable frozen P1.1 reasoning evaluation at **CONTINUE** after a small live accepted-decision check.

**Acceptance-runner correction after `9ecbb4e3`:** the earlier screen read only the last submission call, losing valid evidence/candidates preserved by section-only repair. It now verifies the merged draft against the accepted journal record and ignores later unaccepted calls; explicit offline output folders retain their workspaces. This changes only development acceptance scoring and artifact handling. The same Cloud Shell live accepted-decision check remains the next boundary, then return to comparable frozen P1.1 evaluation at **CONTINUE**.

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
| P2.1 | P2 | Focused read/edit protection live-observed | `175935` rejected a whole-file rewrite using an unissued receipt and continued with targeted edits; complete current-content read coverage remains required for intentional rewrites. Shell edits remain outside this tool contract. |
| P2.2 | P2 | Experimental handoff and authoritative omission live-observed | `173326` successfully used a current-cycle runtime resource in an experimental scan before Intent and omitted that argument for later authoritative scanning. |
| P2.3 | P2 | Same-session mixed recovery live-observed; boundary tested offline | `181746` recovered from seven unknown calls plus one rejected submission; Intent was accepted on shared attempt 9. The tenth-attempt success/exhaustion boundary remains offline-tested only. |
| P2.4 | P2 | Retained retrieval live-observed with limited causal claim | `005510` retrieved two bounded-output ranges successfully, then obtained the decisive Jackson fact through a filtered shell command. Do not credit retrieval alone with the correction. Outcome now also exposes retained final-state/check evidence; its live use remains to verify. |
| P2 | S4 | Implemented architecture; some live paths unobserved | Bounded model-facing outputs + full retained evidence + targeted retrieval + experimental runtime resources. Do not overclaim paths not exercised in clean traces or make optional evidence methods mandatory for P1.1. |
| P3 | S4 | Backlog | Evidence-backed N+1 recovery and first meaningful failure localization; avoid failed-strategy momentum and distinguish strategy vs environment/harness/validation failure. |
| P4 | S3/S4 | Active observed concern | Stale-prior substitution and decision-critical investigation depth remain visible. Recent runs vary: some still call Spring Boot `4.0.6` custom/non-public; another treats it as intentional/custom and preserves it, but without first establishing the parent control point from authoritative evidence. |
| P5 | S5 | Deferred | Runner security, credentials, deployment and ADK Web/Agent Engine adaptation. |
| P6 | P1 | Conditional, not approved | Independent critique or broader branching/search only if clean Experiment 1 evidence justifies complexity. |

**Current position:** S4/P2 evidence work reconciled the previous bookmark `b84863f7` with reviewed head `5902106c`. Three new live runs passed independent validation and delivered Draft PRs #206–208, establishing experimental runtime-resource scanning with later authoritative argument omission, a guarded whole-file write followed by targeted repair, same-cycle unknown-tool recovery on shared attempt 9, and a passing second cycle after failed engineering validation. They did not exercise query-based retained retrieval. One attempt fabricated a reference from `fileSha256`; another used the hex body of a command evidence reference as `read_receipt`. Focused tool-boundary guidance now distinguishes checksum, rewrite receipt, and exact issued evidence reference. A generic retained-evidence fixture is ready for separate offline and live acceptance. Unsupported parent/Jackson explanations remain P1/P4 reasoning concerns. Return to comparable frozen P1.1 evaluation at **CONTINUE** after the small live evidence-use check. See WORK-STATE for exact traces and procedure.

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
