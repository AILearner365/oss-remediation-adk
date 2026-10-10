# OpenHands Gate-2: runtime delivery, stale facts and first-strategy fixation audit

**Date:** 2026-10-09. **Scope:** read-only audit of existing Task-05/06 evidence and pinned OpenHands SDK 1.50.0 sources; current public Gemini and industry documentation. **No Task-07 live run, no runtime/validator/model change.** Qualitative findings are anchored in [Task-05](GATE2-STOP-HOOK-TASK05-ANALYSIS.md), [Task-06](GATE2-STOP-HOOK-TASK06-ANALYSIS.md), and the [nine-dimension scorecard](ENGINEERING-EVALUATION-SCORECARD.md).

## Decision summary

The demonstrable weakness is **failure to verify current, consequential engineering facts before strategy commitment**, followed by **semantic persistence in disproven premises**. These are distinct from SDK/tool absence and from proven training-data staleness. The configured native OpenHands system prompt already requests exploration, alternative comparison, efficient tool use, verification, and reconsideration after repeated failures; the unchanged Gate-2 task explicitly forbids a Spring Boot downgrade. Yet Task-05 E27 and Task-06 E53 both downgrade Spring Boot without establishing supported artifact-family compatibility. Task-06 later makes effective use of authoritative Stop Hook feedback; Task-05 repeatedly loses healthier states. Task-06's successful final validation does not prove best solution or guidance causality.

**Recommendation:** keep Gemini 2.5 Flash, OpenHands SDK 1.50.0, one agent, current tools, Stop Hook, and independent validator unchanged. Evaluate the already-committed opt-in Principle-1 refinement as **one hypothesis**, not a demonstrated fix. Before Task-07, verify the exact effective Vertex/LiteLLM thinking settings (not infer from defaults) and freeze/record environment, task and advisory conditions. No evidence justifies new Skills, web grounding, custom plan enforcement, critic, additional retries or a model/harness switch now.

## 1. Mechanisms: configured, delivered, used, effective

| Mechanism | Configured | Delivered or activated in Task-06 | Observable use/effect | Confidence / limitation |
| --- | --- | --- | --- | --- |
| Native OpenHands prompt | `get_default_agent(llm, cli_mode=True)` | Task-05 and -06 E0 base prompt byte-identical | Agent explored, but did not verify current Boot patch release before E53 | **PROVEN delivery; poor adherence at critical decision** |
| Additional five principles | Runner creates `AgentContext(system_message_suffix=...)` under opt-in flag | Task-06 rendered Dynamic Context matches committed five-line guidance/hash | Reassessed after hooks; still performed prohibited downgrade | **PROVEN delivery; causal improvement NOT PROVEN** |
| Task contract | Parsed `GATE2-TASK.md`, sent via `conversation.send_message(task)` | E1 same hash in Task-05/06 | Explicit no-downgrade violated; final Task-06 honors it | **PROVEN** |
| Terminal/editor/task tracker/finish/think | Native default preset + tool startup | Five available tools verified | Maven/OSV/SBOM/tree tools produced real information, sometimes with invalid flags/misinterpretation | **PROVEN tools and partial effective use** |
| Independent Stop Hook | Configured with native `HookConfig(stop=...)` | Four validation attempts; three denials | Task-06 fixes Boot downgrade promptly after attempt-2 rejection and later fixes coordinates | **PROVEN feedback/recovery; not pre-edit gate** |
| Native stuck detection | `Conversation(..., stuck_detection=True)` | Enabled | Task-05 repeated changed commands/edit patterns while retaining unsupported hypothesis | **PROVEN enabled; semantic protection NOT PROVEN** |
| Native condensation | Native agent/conversation path; recorded events | Task-05 eight, Task-06 four condensations | Earliest invalid downgrade in each occurs before first relevant condensation | **PROVEN occurred; causal context loss UNRESOLVED** |
| Project/user/public Skills | SDK has loading flags; Task-06 runner creates a fresh suffix-only `AgentContext` | `load_project_skills/load_user_skills/load_public_skills` default **False** in pinned `AgentContext` | No Task-06 project Skill effectiveness demonstrated | **Configured flags off in explicit context; no undocumented source assumed** |
| Persistent memory | SDK has `load_memory` default False | No enabling option passed | No demonstrated impact | **Not enabled by explicit Task-06 context** |
| Gemini search grounding | Provider supports optional grounding | No grounding configuration in runner; `LLM(model=..., api_key=None)` | Current facts available via terminal/Maven, no native grounded-search evidence | **Not demonstrated; provider compatibility remains unverified** |
| Gemini thinking configuration | Runner does not explicitly set thinking budget | Usage includes reasoning tokens | Effective provider default/budget not logged in reviewed sources | **UNRESOLVED; requires tightly scoped runtime/config inspection** |

Pinned source: [AgentContext defaults](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-sdk/openhands/sdk/context/agent_context.py), [native prompt](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-sdk/openhands/sdk/context/prompts/sections/static.py), [runner](../../../scripts/openhands/openhands-gate2-stop-hook-run.py), [guidance](../../../scripts/openhands/guidance/engineering-judgment.md), [task](GATE2-TASK.md), [Stop Hook](../../../scripts/openhands/openhands-gate2-stop-hook.sh).

Do not confuse **SDK supports** with **runner enables**, nor **tool available** with **tool called and correctly used**.

## 2. First consequential wrong decision: Task-05 and Task-06

| Question | Task-05 | Task-06 |
| --- | --- | --- |
| Healthy baseline / valid initial progress | Boot 4.0.6, build/scan/policies pass; 2/25 resolved by first validation E23 | Boot 4.0.6, build/scan/policies pass; 2/26 resolved by first validation E51 |
| Contract already available | E1 explicitly prohibits Boot downgrade | E1 same task contract and optional guidance delivered |
| Decision moment | **E27:** Boot 4.0.6 -> **3.2.5**, still retains Boot-4-only `spring-boot-starter-webmvc` | **E53:** Boot 4.0.6 -> **3.2.0**, describes downgrade as upgrade and reworks starter family |
| Verified relevant facts *before* edit? | No observed current-release, coordinate availability or compatibility verification | No observed current Boot patch-line/family check or support evidence for downgrade |
| Immediate counterevidence | E30 missing dependency management; E60 nonexistent webmvc 3.2.5 | E56 missing dependency management; initial builds fail, subsequently changes starter family to make Boot 3 build |
| Does strategy change on contradiction? | Many management/version/cache edits; restores Boot 4 then reverts to older families | Maintains Boot-3 hypothesis until validation attempt 2 E89 reports Boot downgrade + 36 new prohibited findings; E91/E93 restore Boot 4 |
| Fixation persistence | Severe (48 agent Maven installs, 45 failed; four cache deletions; final downgrade 2.7.18) | Shorter (15 agent Maven installs total, six failures; no cache deletion) |
| Preserves healthier state? | No; later discards valid Boot 4 builds | Yes; restored Boot 4 preserved through final PASS |
| Best solution demonstrated? | No; final broken | No; final validator PASS with unverified release-family alignment |

**Interpretation:** Both examples demonstrate bad strategy selection **despite existing instructions and accessible facts**. The initial errors occur before first condensation; do not blame memory loss for the initial move. The exact hidden hypothesis or stale training as a cause is not observable. We can say the model *did not verify* the assumption before commitment; we cannot know whether it internally considered another version and rejected it.

### Current information versus stale knowledge

Gemini 2.5 Flash's [Google model card](https://modelcards.withgoogle.com/assets/documents/gemini-2.5-flash.pdf) states **January 2025 knowledge cutoff** and notes limitations including hallucinations and complex deduction. The 2026 Maven ecosystem postdates this. This is a reason to distrust remembered versions; it does **not** prove the cutoff caused any observed incorrect statement. In Task-06, official Boot 4.0.6 was incorrectly called custom/nonstandard; Maven Central was functioning and could have been consulted. Boot 4.0.8 was an available 2026 alternative but remains **untested** as a complete solution.

### Contradiction-to-revision and evidence yield

- Task-05: E30/E60 directly contradict downgrade assumptions, yet work continues across changed build/edit operations; later healthier states are lost. The number of actions is not a pure efficiency proxy, but this interval has low evidence yield relative to execution.
- Task-06: E56 contradicts initial Boot family assumption, yet the agent first adapts starter family instead of abandoning the prohibited approach; authoritative E89 feedback triggers E91/E93 rollback. Later SBOM scanner findings drive corrected Jackson coordinates. This is better **late-stage** evidence use, not reliable pre-commitment judgment.
- Future scorecards should record: **decision / factual assumption / authoritative evidence available / actual fact-check before edit / first contradictory observation / first meaningful revision / unnecessary actions / retained healthier state**. These are sub-measures of the existing nine dimensions, not new runtime controls.

## 3. Gemini settings and grounding boundary

The runner constructs `LLM(usage_id="openhands-gate2-stop-hook", model=args.model, api_key=None)`, without an explicit `thinking_budget`, grounding tool, external search connector or separate Google Search configuration. Gemini 2.5 Flash has documented thinking/function-calling/grounding capabilities, but model support alone does not prove they were active in this Vertex/OpenHands path. Captured reasoning-token usage shows some model reasoning accounting, **not the effective thinking-budget setting**.

Current source evidence does **not** establish final provider-request parameters, provider defaults, grounding/tool composability or whether env-specific settings altered inference. These require a **configuration-only Cloud Shell check** if we decide the uncertainty is material. Do not expose credentials or raw protected traces; avoid any model call solely to query defaults if source/config inspection suffices.

References: [Gemini model card](https://modelcards.withgoogle.com/assets/documents/gemini-2.5-flash.pdf), [Gemini models](https://ai.google.dev/gemini-api/docs/models), [Vertex grounding overview](https://cloud.google.com/vertex-ai/generative-ai/docs/grounding/overview).

## 4. Other-agent practice: comparable mechanisms, not performance rankings

| Ecosystem | Documented mechanism | Relevance / limitation |
| --- | --- | --- |
| OpenAI / Codex | AGENTS.md for persistent repository instruction; configurable tools and web search for live facts; evaluations and workflow tests | Instructions and current tools are separate; an AGENTS.md does not itself verify release metadata or force good decisions. [OpenAI internal Codex practices](https://openai.com/business/guides-and-resources/how-openai-uses-codex/), [web search setup](https://developers.openai.com/api/docs/guides/agents-api/tools/web-search) |
| Claude Code | Project instructions/Skills, tool permissions/hooks, test-driven and verification practices | Supports workflow controls; no proof that a general instruction prevents incorrect first strategies under our Gemini task. [Claude Code best practices](https://code.claude.com/docs/en/best-practices) |
| SWE-agent | Purpose-built agent/computer interaction and feedback for repository tasks | Tool usability and feedback quality affect agent ability to recover. [SWE-agent paper](https://arxiv.org/abs/2405.15793) |
| OpenHands | Native prompts, Skills, tool observations, hooks, optional Critic, condensation | Our setup already uses core tools/feedback; optional Critic adds unproven service dependency. [OpenHands SDK overview](https://www.openhands.dev/blog/introducing-the-openhands-software-agent-sdk), [Critic assessment](OPENHANDS-CRITIC-FEASIBILITY.md) |
| General research | ReAct: external observations to revise actions; Reflexion: feedback-based reflective retries; trajectory evaluation reveals lucky passes | Supports observation-driven problem-solving and process evaluation, **not** a claim that implementing another autonomous loop is required. [ReAct](https://arxiv.org/abs/2210.03629), [Reflexion](https://arxiv.org/abs/2303.11366) |

No cross-harness study here demonstrates that Codex, Claude Code or SWE-agent outperforms the *same Gemini 2.5 Flash model* under our exact task, prompt, tools, bounds and validator. Do not claim a competitive win or recommend an OpenCode switch.

## 5. Task-07 readiness: what is justified

**Already committed as an opt-in treatment:** Principle 1 was changed from a generic evidence check to requiring **current authoritative evidence** before consequential changes and meaningful comparison of materially different credible candidates. Four other principles stay unchanged. This targets the exact E27/E53 failure mechanism but may still be ignored. Do not add a prompt list, Skill, stronger model, custom stopping policy or extra checks.

**Before running:**
1. Record the precise guidance commit/hash used for historical Task-06 and the new candidate. Verify the option is explicitly enabled, and the system-context suffix is rendered exactly.
2. Freeze/record task prompt SHA, Gemini 2.5 Flash model path, SDK 1.50.0, five tools, stuck detection, condenser, hook/validator, baseline commit, advisory identities and the iteration/denial bounds. Advisory drift was already observed (25 vs 26).
3. Verify **what can be proven** about effective thinking/tool/grounding settings without changing them; mark other settings unresolved.
4. Evaluate **pre-commitment evidence gathering and first strategy choice** (especially E27/E53 analogues) in addition to recovery, solution alignment, time/cost/edits and final PASS.
5. Attribute any improvement only as observation; one run cannot prove the guidance caused it.

**No new runtime components justified.** Native prompt and existing suffix already cover general alternatives and reflection. The model's failure to follow instructions is **not evidence that another prompt or orchestration layer is needed**. If the refined guidance repeatedly fails, the next investigation should isolate why available evidence is not being queried/used, rather than adding more synonyms for 'verify'.

## 6. Validation and scope boundaries

This review is based on repository sources, published Task-05/06 trajectories and external documentation. We did **not** run Gemini, reconstruct hidden thoughts, obtain raw provider request payloads, exercise ground search, run a new target patch, or demonstrate a controlled causal improvement. Effective provider-side thinking settings and complete post-condensation context are **UNRESOLVED**. Review is documentation-only.
