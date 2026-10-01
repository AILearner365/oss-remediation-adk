# Harness design review — agreed concerns and next work

Recorded: 2026-09-29. Review baseline: AILearner365/oss-remediation-adk, branch context-hygiene-clone-challenge-before-commitment, commit d931c3fcaf79d6c8e4a48b8db88651a06714f3d1. This is a development review record, not runtime instructions. No runtime changes are made by this note.

## User objective and scope

Review the overall architecture and implementation against established harness-engineering practices. Address unnecessary model-facing bookkeeping and restrictions before adding further reasoning instructions. A new comparative quality experiment is not a prerequisite for correcting demonstrated interface and reliability defects.

Preserve company-required GitHub, OSV/JFrog Xray, approved network, proxy, certificate and authentication arrangements. Custom adapters are legitimate. Review what they expose to the model, how they preserve evidence, and how failures propagate. Do not confuse necessary enterprise transport constraints with avoidable formatting or content restrictions.

## Overall judgment

The top-level architecture is broadly aligned: a model-directed engineering loop within deterministic preparation, validation and delivery boundaries. The implementation is only partially aligned with robust harness practices: it has useful modular capabilities, bounded/retrievable evidence and independent validation, but also burdensome checkpoint serialization, failure coupling and incomplete durable-session recovery. This is a targeted responsibility-boundary refactor, not evidence for replacing the entire architecture or choosing another framework.

There is no single industry-certified harness blueprint. Published production patterns and established open-source implementations support stable tool interfaces, clear errors, recoverable history and model-directed action. They do not establish that a detailed pre-implementation questionnaire is required, or guarantee optimal solutions.

## Responsibility boundary

The model owns investigation, engineering judgment, candidate selection, implementation, reassessment and concise explanations of material decisions and uncertainty.

The harness owns schemas, permissions, execution dispatch, lifecycle state, bounded recovery, durable evidence, provenance, budgets, deterministic checks, delivery and rendering audit documents. It may ask the model for decision information that cannot be derived from tools. It should derive tool chronology and other observable bookkeeping automatically. It must not invent reasoning on the model's behalf.

## Findings and intended work

| Area | Evidence at reviewed revision | Intended direction |
|---|---|---|
| Checkpoint contract | journal.py validates exact Markdown tables, candidate headings and labels inside JSON; errors request complete resubmission. | Keep meaningful decision information; use a compact typed interface and deterministic document rendering. Support localized correction. |
| Capability visibility | toolset.py registers all tools while phase checks reject some invocations. | Align model-visible tools with usable capabilities where ADK supports safe dynamic exposure; always retain server-side enforcement. |
| Error isolation | agent.py propagates unknown-tool exceptions; orchestrator.py can fail capture, validate and recreate the session. | Handle recoverable invocation failures locally with bounded feedback. Do not equate every protocol failure with a new engineering cycle. Preserve protocol integrity when recovering. |
| Durable history | Session recreation resets the artifact counter. Latest run references 000001.json for three different oversized messages. | Unique run-wide event/artifact identity; immutable history independent of session lifetime; retrievable recovery evidence. |
| Recovery context | Replacement sessions receive journal/validation context, not the full prior conversation. | Supply concise supported state and references to material evidence, including evidence from unsuccessful capture attempts. Avoid copying every old message or treating prior conclusions as facts. |
| Evidence access | Latest run has two search extraction failures; research_fetch rejects a Maven POM as text/xml. | Preserve authorized source content and provenance; support relevant formats with typed status and targeted retrieval. Keep network/authentication restrictions intact. |
| Evidence presentation | Bounded tool responses and retained references exist. | Preserve this design; distinguish failed acquisition, partial extraction, bounded display and completed results. The wrapper must not make obtainable evidence unusable. |
| Independent validation | Successful delivery and withheld delivery are both observed. | Retain checks and delivery gates; scope success claims to tested properties. |

## Immediate work and limits

Treat these concerns as one coherent interface/responsibility review, with focused regression verification: valid checkpoint submission, precise malformed-input recovery, unavailable-tool handling, session replacement, immutable artifacts, evidence format support and retrieval. Begin with the checkpoint boundary and error/state contracts; fix trace integrity as part of that work.

Do not add new agents, mandate scanner calls, prescribe a Spring/Maven remediation strategy, or expand Q1–Q5 merely to address wrapper failures. Proposed checkpoint simplification is a design direction, not an already implemented change. Functional tests can verify these contracts; they cannot establish improved engineering judgment. Whether the agent chooses stronger solutions remains a separate unresolved question.

## Evidence references

- Repository baseline: https://github.com/AILearner365/oss-remediation-adk/tree/d931c3fcaf79d6c8e4a48b8db88651a06714f3d1
- Active code: autonomous_oss_remediation_agent/{agent.py,orchestrator.py,journal.py,prompt.py,capabilities/toolset.py,capabilities/research.py,deterministic/validation.py}.
- Latest trace: autonomous-oss-remediation-workspaces/run-20260929T022558Z-6343141c/artifacts/events.jsonl.
- Production separation of session, harness and execution: https://www.anthropic.com/engineering/managed-agents
- Economical context and clear tool contracts: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Evaluation-driven tool design: https://www.anthropic.com/engineering/writing-tools-for-agents
- Minimal coding-agent reference: https://mini-swe-agent.com/latest/

External examples support the principles, not a claim that their complete architectures must be copied. No new live runs or independently rerun tests underpin this review.

## October 1 handoff reconciliation

This note preserves the September 29 review; its defect descriptions are historical findings, not a claim that all remain present at the current head. At handoff preparation, branch head was 1d04423202c8a62cddfbc6a3a7c3070b98b47ed9. Inspection of agent.py confirms an Intent-phase unknown-tool callback and unique per-session artifact namespace were added. The commit and continuity documents report focused tests; this documentation handoff did not rerun them or establish live acceptance.

Current user direction: reconcile those fixes, then implement the remaining responsibility-boundary cleanup using the adjacent [Codex implementation prompt](CODEX-IMPLEMENTATION-PROMPT.md). A general quality comparison or live run is not a prerequisite for demonstrated interface repairs. Existing company integrations remain constraints. Update project continuity as implementation progresses; do not inject these review documents into the runtime agent.
