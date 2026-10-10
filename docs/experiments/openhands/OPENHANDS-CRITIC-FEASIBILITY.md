# OpenHands SDK 1.50.0 native Critic — focused feasibility assessment

Date: 2026-10-09. Scope: **READ-ONLY source assessment** for the existing Vertex Gemini 2.5 Flash Gate-2 system. No runtime tests, credentials, Critic deployment, SDK upgrade or remediation run. **Decision: DO NOT INTEGRATE the bundled Critic into the current Gate-2 runtime yet.** It is an available experimental extension but not a verified minimal correction for the nine-dimension gaps.

## Why we evaluated it

[Engineering evaluation standard](ENGINEERING-EVALUATION-SCORECARD.md) identifies Task-05/06 weaknesses in **unsupported initial strategy selection, unverified/current-version claims, credible-alternative selection, release-family alignment, and avoidable action/tool churn**. Task-06 recovery improved but still repeated the forbidden Boot downgrade before a Stop Hook contradicted it. A useful Critic must intervene **before or near bad consequential decisions**, with sufficiently specific feedback, and must not duplicate final deterministic validation or create a second autonomous engineer.

## Direct SDK 1.50.0 source findings

Inspect the pinned upstream source, not newer documentation:

- [CriticBase](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-sdk/openhands/sdk/critic/base.py): optional `critic`; `mode="finish_and_message"` by default; optional `mode="all_actions"`; optional bounded `IterativeRefinementConfig` with `success_threshold` and `max_iterations`.
- [AgentBase](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-sdk/openhands/sdk/agent/base.py): `critic: CriticBase | None` marked **EXPERIMENTAL**; API/behavior can change and all-action mode can impact performance.
- [CriticMixin](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-sdk/openhands/sdk/agent/critic_mixin.py): `_should_evaluate_with_critic` evaluates every action only in `all_actions`, otherwise FinishAction (message handling in step). `_evaluate_with_critic` passes the LLM-convertible event history and **`git_patch=None`**; exceptions are logged and return `None`. Iterative-refinement continuation checks occur after FinishAction and can issue generic follow-up, not a guaranteed pre-edit decision gate.
- [APIBasedCritic](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-sdk/openhands/sdk/critic/impl/api/critic.py): builds a trace from the condenser-retained view, converts to chat/tool payload, calls a classification endpoint, returns a **success probability and broad taxonomy labels**, not an authoritative compatibility/verifier judgment. Categories include insufficient analysis, loop behavior, tool misuse, insufficient testing, scope creep and infrastructure issues.
- [CriticClient](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-sdk/openhands/sdk/critic/impl/api/client.py): separate `server_url`, required `api_key`, `model_name`, tokenizer/template and **vLLM `/classify`** endpoint; HTTP timeout defaults to 300 seconds with retries for 500 responses. Its inference path does **not** invoke the existing Vertex Gemini chat configuration automatically.
- [AgentFinishedCritic](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-sdk/openhands/sdk/critic/impl/agent_finished.py): checks final FinishAction and nonempty git patch. Since the current mixin calls critics with `git_patch=None`, this built-in implementation would score an empty patch, and is not a sound choice for this Gate-2 run.

These are verified **source contracts**, not demonstrations of the installed package executing against the user's credentials/environment.

## Feasibility against the four questions

| Question | Finding | Evidence status |
| --- | --- | --- |
| 1. Can it evaluate while work progresses, before a bad strategy completes? | `all_actions` can invoke classification after each agent action, so **intermediate observation is natively possible**. Source does not establish a pre-tool blocking/replanning decision, nor demonstrate that the agent receives/usefully applies a decision-specific signal before selecting an invalid dependency version. The built-in bounded refinement acts at completion. | **PARTIAL** |
| 2. Can it detect unsupported assumptions, contradiction handling, credible alternatives, family alignment or wasted work? | Generic success/issue taxonomy includes insufficient analysis and looping, but no demonstrated per-dependency fact-checking, release-train verification, actionable alternative ranking, or per-action causal explanation. On the real Task-05/06 trajectories, accuracy is **NOT TESTED**. | **UNRESOLVED** for our nine dimensions |
| 3. What are extra dependencies/costs? | `APIBasedCritic` requires a separate vLLM-compatible classification service, credentials, tokenizer/template, and possibly a non-Gemini model; it sends retained agent trace/tool definitions. All-action mode could generate up to one remote classification call per action (Task-06: 118 actions, Task-05: 193), before retries; trace size and costs are not measured. Service provisioning, network/credential policy, Vertex compatibility, model quality and latency are **UNVERIFIED**. | **PROVEN source dependencies; costs UNRESOLVED** |
| 4. Minimal integration beyond guidance + Stop Hook? | Agent has native `critic` attachment (small configuration change), but production-useful API Critic is not turnkey in the pinned Vertex setup; finish-time critic overlaps deterministic validation, while all-action mode introduces many calls without demonstrated intervention value. `AgentFinishedCritic` is unsuitable under the observed null patch path. | **DO NOT INTEGRATE YET** |

## Risks and constraints

- **Timing mismatch:** we need stronger judgment *before choosing* Boot downgrade or unverified version, rather than another completion scorer.
- **Signal quality:** a broad classifier labeling “insufficient analysis” does not independently prove the specific artifact or release version correct.
- **Independence:** learned classification must never override authoritative build/security/policy validator; do not grant model-written confidence the status of evidence.
- **Overhead:** all-action classification can increase latency/cost and context traffic substantially. Even partial incremental use requires evidence of utility before activation.
- **Model/service availability and privacy:** endpoint, credentials, transcript transfer, environment policy and Vertex support remain unverified. Do not assume access to default OpenHands-hosted service.
- **Failure modes:** swallowed Critic exceptions may silently remove feedback; refinement could create overlapping retries with the three-denial native Stop Hook; a final judge is not a tested solution-quality check.
- **Experimental comparability:** introducing Critic, another model, and more calls changes several factors simultaneously. Existing Task-05/06 findings cannot establish Critic benefit.

## Decision and smallest evidence-driven next action

**Decision: DO NOT IMPLEMENT the API Critic on the current run.** It is available as a native hook point, but the upstream SDK 1.50.0 implementation does **not** yet demonstrate an economical, reliable intervention against our highest-priority failures. This is *not* a declaration that Critic research lacks merit; it is a boundary against integration without task-specific evidence.

1. Keep the five-principle opt-in engineering guidance unchanged; retain the nine-dimension scorecard and independent Stop Hook validator.
2. For technical correctness and best-solution quality, perform the already identified **read-only dependency-family alignment and credible-alternative review** of Task-06's captured patch, including what sources were available *before* each consequential choice. Do not retrofit a vulnerability recipe into the agent.
3. Only revisit native Critic if a **specific compatible classification service and low-cost offline scoring of existing Task-05/06 trajectories** becomes available. Test whether it flags E27/E53 and unreconciled family mismatch *early and reliably*, how scores map to actionable decisions, latency/cost and false positives. An offline proof is a prerequisite to any opt-in live integration; don't implement custom orchestration for this.
4. If improving outcomes is prioritized instead of Critic research, a small controlled comparison using the existing guidance and same-advisory controls is more directly interpretable than adding another model/service.

**Platform decision remains CONTINUE EVALUATION.** No Gate-2 code, prompt, task, target, validator, Stop Hook, retry bound or existing evidence was modified by this assessment.

## References

- [Task-05 evidence and assessment](GATE2-STOP-HOOK-TASK05-ANALYSIS.md)
- [Task-06 evidence and assessment](GATE2-STOP-HOOK-TASK06-ANALYSIS.md)
- [Standard nine-dimensional scorecard](ENGINEERING-EVALUATION-SCORECARD.md)
- [Native Critic base](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-sdk/openhands/sdk/critic/base.py)
- [Native Critic integration](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-sdk/openhands/sdk/agent/critic_mixin.py)
- [API-based classifier](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-sdk/openhands/sdk/critic/impl/api/critic.py)
- [Classifier endpoint client](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-sdk/openhands/sdk/critic/impl/api/client.py)
