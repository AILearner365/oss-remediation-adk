# Task-07 reproducible configuration audit and execution readiness

Date: 2026-10-09. Status: **SOURCE VERIFIED / LIVE ENVIRONMENT NOT ACCESSIBLE IN THIS SESSION**. The control repo was inspected via the GitHub connection; this is not a replay of the Cloud Shell runtime or a Task-07 live run.

## Source-verified configuration

| Setting | Actual source configuration | Verification |
| --- | --- | --- |
| Runtime launcher | `scripts/openhands/openhands-gate2-fresh-run.sh 07` calls startup, verification and `openhands-gate2-execute.sh 07` | Direct script inspection |
| SDK/tools | `uv run --with "openhands-sdk[vertex]==1.50.0" --with "openhands-tools==1.50.0"` | Execute script |
| Model | `MODEL` default `vertex_ai/gemini-2.5-flash` | Execute script/runner |
| Working tree | Separate `openhands-poc-task-07-stop-hook` target branch/worktree initialized at configured source baseline | Execute script |
| State | Dedicated `~/.openhands/gate2/task-07-stop-hook` | Execute script |
| Agent | `get_default_agent(llm=llm, cli_mode=True)` | Runner |
| Guidance | `OPENHANDS_ENGINEERING_JUDGMENT_GUIDANCE=1` enables `AgentContext(system_message_suffix=...)` | Runner; ensure environment flag set for Task-07 |
| Native project/user/public Skills | AgentContext default flags False under explicit suffix-only context | Pinned SDK source; no alternate loading path shown in runner |
| Native memory | `load_memory=False` default | Pinned SDK source |
| Native stuck detection | `stuck_detection=True` | Runner |
| Conversation | `persistence_dir=state_dir/conversation`, `delete_on_close=False` | Runner |
| Max iterations | Default 250 | Execute script and runner |
| Stop Hook | Native `HookConfig(stop=...)`; default max three denials | Runner and hook |
| Validator | Independent native Stop Hook calls `openhands-gate2-validate.sh` | Hook script |
| Task | `GATE2-TASK.md` section extracted and sent as initial user message | Runner |
| External grounding | No explicit Gemini Google Search grounding configuration in inspected runner | Not proven active; outside runtime SDK wiring not established |
| Thinking budget | No explicit budget/temperature/thinking parameter in constructed LLM | Effective provider request parameters **UNRESOLVED** |
| Advisory identities | Baseline script generates initial identities | Need live Task-07 baseline snapshot; Task-05/06 advisory drift observed |
| Prompt delivery | Task-06 dynamic context proved engineering suffix delivered | Task-07 **not yet exercised** |

Source files:
- [fresh-run orchestration](../../../scripts/openhands/openhands-gate2-fresh-run.sh)
- [worktree/launcher](../../../scripts/openhands/openhands-gate2-execute.sh)
- [runner and model setup](../../../scripts/openhands/openhands-gate2-stop-hook-run.py)
- [engineering guidance](../../../scripts/openhands/guidance/engineering-judgment.md)
- [task](GATE2-TASK.md)
- [hook](../../../scripts/openhands/openhands-gate2-stop-hook.sh)
- [nine-dimensional scorecard](ENGINEERING-EVALUATION-SCORECARD.md)
- [pinned AgentContext flags](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-sdk/openhands/sdk/context/agent_context.py).

## Exact Task-07 treatment and scope

Guidance Principle 1 now reads:

> Before a consequential engineering change, verify decision-critical facts against current authoritative evidence rather than relying on remembered or assumed versions, capabilities, or compatibility. Where materially different credible approaches exist, compare their constraints, compatibility, maintainability, and downstream impact before selecting one.

Only Principle 1 differs from historical Task-06 guidance. Other four principles, task contract, model, SDK, tools, stop hook and validator intended unchanged. The principle is **opt-in**, so explicitly set `OPENHANDS_ENGINEERING_JUDGMENT_GUIDANCE=1` for Task-07. Control comparisons are limited by changing scanner advisories and model sampling.

## Live invocation (Cloud Shell only)

Review working branch and startup configuration before launch; use a clean, up-to-date control checkout. Existing orchestrator both prepares a fresh target and captures/pushes run evidence. On Cloud Shell (not this GitHub-only session):

```bash
cd ~/oss-remediation-adk
git switch openhands-poc-evaluation
git pull --ff-only
export OPENHANDS_ENGINEERING_JUDGMENT_GUIDANCE=1
bash scripts/openhands/openhands-gate2-fresh-run.sh 07
```

Do not execute from a checkout with local changes that would be overwritten, or if Task-07 worktree/state already exists. Use existing Cloud Shell startup / credential configuration; never paste credentials into evidence, prompts or logs.

## Postrun validation contract

1. Confirm Task-07 run metadata, control SHA, target baseline, advisory identities, model/SDK, and guidance-on marker.
2. Confirm the **rendered** Task-07 dynamic context contains the exact Principle-1 treatment (not merely an enabled marker).
3. Confirm validator report and complete scanner inventory; separate PASS from engineering-quality acceptance.
4. From exported trajectory events, extract first consequential engineering change; its supporting current facts and sources *prior to edit*; contradictory evidence and subsequent strategy revision; credible alternatives, healthier states, and evidence yield.
5. Score all nine established dimensions (qualitative rating and independent evidence confidence); include time/cost/build/scan/editor churn.
6. Explicitly mark unobserved effective Gemini thinking/grounding configuration, post-condensation model context or hidden reasoning as UNRESOLVED.
7. Compare with Task-05 and Task-06 without attributing any apparent improvement to guidance on one run; preserve those original assessments.

## Execution limit

The GitHub integration available to this assistant can read and update repository content, but offers **no Cloud Shell process execution, remote shell, Vertex impersonation, or GitHub workflow dispatch**. Accordingly no Task-07 run has been launched, no new agent trajectory exists, and runtime-specific unknowns cannot be claimed verified. Do not claim this read-only config report establishes effective provider-side parameter defaults. The executable command above must be run in the Cloud Shell environment with authorized access.
