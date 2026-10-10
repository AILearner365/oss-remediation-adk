# Current-information and strategy-commitment audit — Task-07 hypothesis

Date: 2026-10-09. **RESEARCH AND STATIC SOURCE REVIEW; NO LIVE TASK-07 EXECUTION.** Scope: Gemini 2.5 Flash, OpenHands SDK 1.50.0, Task-05/06 evidence, broader coding-agent practices. Read alongside [nine-dimension standard](ENGINEERING-EVALUATION-SCORECARD.md), [Task-05 analysis](GATE2-STOP-HOOK-TASK05-ANALYSIS.md), and [Task-06 analysis](GATE2-STOP-HOOK-TASK06-ANALYSIS.md).

## Summary and decision

Two related failures must be distinguished: **(a) stale/incorrect facts** about a changing environment and **(b) strategy commitment/fixation** after evidence contradicts assumptions. Task-06 proves the agent made false Spring Boot release assertions, selected unsupported versions and failed to inspect the currently allowed patch line before choosing a strategy; it does not prove those errors came specifically from Gemini's training cutoff. Task-05 shows repeated regressions even after passing Boot 4 builds. Task-06 shows shorter fixation and effective response to explicit Stop Hook feedback, but still repeats the initial forbidden downgrade.

**Decision:** retain one model (Vertex Gemini 2.5 Flash), SDK 1.50.0, native tooling, one autonomous agent, bounded native Stop Hook, and deterministic validator. Make a *single opt-in, technology-neutral guidance change* to Principle 1: explicitly prefer **current authoritative evidence** to memorized version/capability claims and compare materially distinct credible alternatives when warranted. Leave other four principles unchanged. This is a **hypothesis for Task-07**, not an established correction. Do not add a web proxy, Critic, another model, Skills, custom planner, scripted strategy selector, remediation recipe or additional retries.

## 1. Model perspective: Gemini 2.5 Flash and changing facts

- [Google's Gemini model documentation](https://ai.google.dev/gemini-api/docs/models#gemini-2.5-flash) documents model capability, supported tools and a **January 2025 knowledge cutoff** for Gemini 2.5 Flash. The October 2026 dependency ecosystem postdates that cutoff. This makes relying on remembered Spring Boot releases inappropriate; **it does not identify the cause of a particular false statement**.
- [Google Search grounding](https://ai.google.dev/gemini-api/docs/google-search) and [Vertex AI grounding overview](https://cloud.google.com/vertex-ai/generative-ai/docs/grounding/overview) explain optional retrieval of recent external information. Support at the model/API level is **not evidence** that the currently configured OpenHands -> Vertex path enables grounding.
- [Function calling](https://ai.google.dev/gemini-api/docs/function-calling) and tools allow external checks. Actual Task-06 terminal/Maven/OSV access was sufficient to retrieve authoritative package metadata; there is **no demonstrated missing search-tool capability**.
- Gemini's thinking capability does not guarantee fact checking or optimal engineering decisions. A model can reason coherently from a false premise; relying on proprietary internal reasoning or inferring its exact mental cause from tool traces is not sound evidence.

## 2. Native OpenHands 1.50.0 perspective

Pinned upstream sources:
- [Native problem-solving prompt](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-sdk/openhands/sdk/context/prompts/sections/static.py): explicitly says **explore relevant files**, **consider multiple approaches/select promising one**, make focused changes, **verify**, and on repeated failure reconsider multiple possible causes. Generic efficient file exploration and testing guidance exists.
- [Agent and optional context](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-sdk/openhands/sdk/agent/base.py) and [AgentContext](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-sdk/openhands/sdk/context/agent_context.py): opt-in `system_message_suffix`; support Skills and project context. None is a built-in mandatory release-fact lookup or evidence-before-edit decision gate.
- [Critic source](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-sdk/openhands/sdk/critic/base.py): optional experimental classification with finish/message or all-action modes; see [previous feasibility review](OPENHANDS-CRITIC-FEASIBILITY.md). Not established as solution to version verification or initial strategy selection.
- Native stuck detection primarily detects repeated action patterns, not varied edits preserving a wrong semantic premise. Condensation can change retained context, but initial downgrade in both Task-05/06 happened before relevant condensation; it is **not the established origin** of these errors.
- OpenHands SDK's generic alternative consideration is not the same as factual validation of a candidate's *current existence and compatibility*.

## 3. Current POC inputs and observed value

| Delivered mechanism | Timing and input | Scorecard relevance | Task-05/06 finding |
| --- | --- | --- | --- |
| Native SDK prompt | Initial model-facing system message | Investigation, alternatives, verification, efficiency | Alternative consideration is present but not reliably followed. |
| [Task contract](GATE2-TASK.md) | Once via `conversation.send_message` | Constraints, correctness, technical justification | Patch/minor Boot upgrades allowed; downgrades forbidden. Same task hash across 05/06. |
| [Engineering principles](../../../scripts/openhands/guidance/engineering-judgment.md) | Task-06 opt-in `AgentContext.system_message_suffix` | All nine, especially assumptions/reassessment | Exact delivery **PROVEN**, causal benefit **NOT PROVEN**; first principle did not prevent downgrade. |
| Tool results (Maven, source, SBOM, scanner) | Following model-owned calls | Current facts, technical accuracy, downstream impact | Authoritative version/coordinate information was available; later used effectively, early calls incomplete/incorrect. |
| Native completion Stop Hook / deterministic validator | When model tries to finish | Acceptance, recovery, constraint feedback | Prompt names concrete findings/policy violations; Task-06 recovery after attempted finish is good, but it does not proactively fact-check decisions. |
| Native stuck detection/condenser | As runtime conditions arise | Fixation, context use | Not proven to prevent semantic fixation or preserve all decision-relevant facts. |

## 4. Strategy fixation and stale-information case evidence

- Task-05 initial forbidden Boot 4.0.6 -> 3.2.5 change at E27; missing starter coordination at E30/E60; many repeated invalid edits/builds and later lost temporarily healthy Boot 4 states.
- Task-06 initial Boot 4.0.6 -> 3.2.0 change at E53 despite prompt and guidance. Agent falsely characterized official 4.0.6 as custom/outdated (E88/E209), tried speculative Spring BOM versions and wrong Jackson family before using observable Maven/SBOM evidence.
- Boot 4.0.8 had been published before Task-06; its BOM manages Spring 7.0.9, Micrometer 1.16.7, Tomcat 11.0.24 and Jackson 3.1.5. This was a **credible candidate**, not a proved superior or complete solution. [Maven Central BOM](https://repo.maven.apache.org/maven2/org/springframework/boot/spring-boot-dependencies/4.0.8/spring-boot-dependencies-4.0.8.pom).
- The exact mental reason for choosing Boot 3 is **UNRESOLVED**. Incorrect release claim **PROVEN**; stale training as cause **UNRESOLVED**; failure to check current authority before consequential change **PROVEN**.
- Task-06 restored Boot 4 after attempt-2 validation feedback and did not relapse; stronger feedback uptake **OBSERVED**, guidance causality **NOT PROVEN**.

## 5. Broader engineering-agent practice: what transfers and what does not

- **Grounded retrieval / tools:** Check authoritative, task-specific current facts using available retrieval or package-manager tools before committing to high-impact changes. Search grounding may be useful in general, but adds API/provider configuration and uncontrolled provenance; existing terminal/Maven access is sufficient in this POC. Verify source trust and freshness.
- **Repository conventions/instructions:** Coding-agent harnesses (including OpenHands Skills / AGENTS.md and comparable coding-agent instruction files) place durable constraints and workflow guidance in context. This helps communicate expectations but **cannot enforce that a model reasons correctly**. [Codex AGENTS.md guidance](https://developers.openai.com/codex/guides/agents-md/) and [Claude Code best practices](https://code.claude.com/docs/en/best-practices).
- **Tests, tool feedback and independent evaluation:** Deterministic builds/security checks catch invalid outcomes and supply counter-evidence. They do not select the best solution before edits or establish cross-family compatibility. [SWE-bench](https://www.swebench.com/) and current software-agent evaluation research distinguish task pass rate from trajectory/engineering quality.
- **Reflection/reassessment:** Correct assumptions in light of contradicted evidence rather than automatically persisting with an initial plan. [Reflexion](https://arxiv.org/abs/2303.11366) and [ReAct](https://arxiv.org/abs/2210.03629) offer general evidence-driven interaction concepts; neither proves that adding a new planning/reflection framework to this POC would be productive.
- **Process- or trajectory-aware evaluation:** Assess avoidable loops, unsupported strategy commitments, regressions and quality of testing in addition to task PASS. We already capture events and maintain a nine-dimensional scorecard. Do not infer internal thoughts from observable actions.

These industry patterns are **design guidance, not experimental proof** that any single prompt or tool will fix Gemini 2.5 Flash in this harness.

## 6. Options considered and decisions

| Intervention | Plausible benefit | Additional cost/risk | Decision |
| --- | --- | --- | --- |
| Keep all existing guidance, no change | Minimal, good comparability | Does not test a new hypothesis for persistent initial error | Retain as reference/control |
| **Refine Principle 1 only** | Emphasizes current authoritative facts and a limited credible-alternatives check before high-impact edits | Model may still ignore; possible slight token/efficiency effect | **Chosen opt-in Task-07 candidate** |
| Replace prompt with larger planning template | May force more explicit planning | Prompt bloat, constrains model-owned strategy, weak attribution | Reject |
| Add new Skills / AGENTS.md | Can deliver reusable task context | Duplicates current instructions and may change baseline | Defer |
| Enable Gemini/Vertex Google Search grounding | More current web data | Integration/provider compatibility, sources, costs, nondeterminism need separate proof | Defer; no proven tooling gap |
| Add separate search/Maven query hook | Could supply live facts | Risks forcing unnecessary calls or introducing recipe/checkpoint | Do not implement |
| Native API-based Critic | Generic issue score | Extra vLLM service/calls; early strategy prevention unproven | Do not integrate |
| More Stop Hook validation/retries | More opportunities to recover | Does not prevent initial unsupported decision; higher cost | Reject |
| Stronger model / OpenCode | Could isolate source of error | Explicitly outside current user scope | Excluded |

## 7. Exact minimal change and testing contract

Only first bullet changed in [engineering-judgment.md](../../../scripts/openhands/guidance/engineering-judgment.md).

**Before**:
> Verify decision-critical assumptions using available evidence before committing to a consequential strategy.

**After**:
> Before a consequential engineering change, verify decision-critical facts against current authoritative evidence rather than relying on remembered or assumed versions, capabilities, or compatibility. Where materially different credible approaches exist, compare their constraints, compatibility, maintainability, and downstream impact before selecting one.

Other four bullets byte-for-byte unchanged. Guidance stays **opt-in** with the existing flag; disabled/default path remains unchanged. No Boot/version/Maven details in guidance.

Before any Task-07 treatment run: freeze task hash, baseline and advisory identity snapshot where feasible, model, inference settings, SDK, tools, hook, validation, bounds and evidence capture. Do **not** alter the task prompt or terminal tools simultaneously. Preserve Task-06 guidance text/hash as historical treatment; do not overwrite evidence. The Task-07 evaluation must check **observable upstream behavior** (authoritative lookups before key edits, candidates and rationale where material, assumptions revised after failure, constraint preservation, avoidable calls) as well as deterministic PASS. Use all nine dimensions. **One improved run cannot prove causality.** If data drifts, report comparability limitation.

## 8. Remaining uncertainty

No live Task-07 run or isolated alternative build was executed in this audit. No current-model grounding integration, future SDK feature or Critic accuracy was tested. The SDK native prompt's exact *rendered* Task-06 delivery was previously established from logs; this audit cross-checked its pinned source rather than claiming access to hidden model state. Version-control changes are limited to opt-in guidance, this research note, and a durable project-memory update.
