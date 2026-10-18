# Native-first OpenHands simplification review

**Date:** 2026-10-18  
**Branch:** `openhands-service-integration`  
**Review scope:** `openhands_shared` and native POC1–4.  
**Status:** design/decision record only. No production component deleted or rewritten.

## Decision

Prefer **one native OpenHands Agent Server conversation** for agent execution, native event history and UI, and **one independent deterministic acceptance authority** for vulnerability validation and delivery authorization.

Simplify custom conversation lifecycle/API/event mirrors after proving per-task identity and recovery parity. Do **not** equate native `finished` or native Stop Hook `ALLOW` with successful remediation.

Minimal logical sequence:

```text
Approved task & exact Git baseline
  -> disposable prepared Git worktree
  -> deterministic baseline (+ optional SBRI intelligence)
  -> native OpenHands conversation edits that SAME worktree
  -> native Stop Hook calls independent deterministic validator
  -> durable PASS + validated workspace state -> delivery authorization
  -> commit/publish exactly validated changes + PR (not implemented)
```

No new separate final-state validation stage or second delivery worktree is proposed. A lightweight validated-state identity check at handoff protects against changes after PASS; it is not a duplicated Maven/OSV scan.

## Evidence: POC 4

| Scenario | Recorded outcome | Acceptance | Native behavior |
| --- | --- | --- | --- |
| Simulated validator infrastructure failure | `INFRASTRUCTURE_FAILURE` | false | terminal ALLOW, `finished` |
| Malformed validator report | `VALIDATOR_FAILURE` | false | terminal ALLOW, `finished` |
| Retry budget exhausted | Four `REMEDIATION_FAILURE` attempts | false | Three DENYs; final ALLOW, `finished` |
| Native Stop Hook exits 37 | Zero validation attempts | false | Hook error did not block `finished` |
| Interrupted validation then reentry | Original attempt reconciled to `VALIDATOR_FAILURE` | false | Native same-conversation continuation, no validator rerun |

Evidence:
- `evidence/native-safety-20261018T194340Z-6ff35a.json`
- `evidence/native-safety-20261018T194522Z-0344d3.json`
- `evidence/native-safety-20261018T194752Z-7179f5.json`
- `evidence/native-safety-20261018T194916Z-1b0885.json`
- `evidence/native-recovery-20261018T200652Z-f80e29.json`

The recovery report's `launcherRestartObserved` compares stored launcher PIDs. The stop/start run also printed `Stored PID refers to a different process`, and an inspection subsequently found a healthy PID 10702 and reachable Server 1.55.1. **Do not claim conclusive server process restart verification.** The interruption is injected in the hook command; real OS kill, real Maven/OSV interruption, delivery authorization, and tamper-resistant isolation remain unproven.

## Component-level review

| Component | Observed responsibility | Native-first disposition | Reason / boundary |
| --- | --- | --- | --- |
| `api.py` | Own `POST /v1/tasks` and task/status/events/artifacts/result GET facade | **Candidate to remove** from default deployment | Native Agent Server supplies conversation create/read/events; need no parallel generic task HTTP service unless an external client demonstrably needs it. Acceptance/evidence retrieval still needs an accessible path (CLI/file or thin endpoint if proven necessary). |
| `openhands_runtime.py` | Custom REST transport, pinned 1.50.0 compatibility, create/reconcile conversation, attach context, execution dispatch, event linking | **Substantially simplify** | Native Server/SDK 1.55.1 POC1–4 already creates, resumes, runs and records conversation/events. Retain only task↔conversation binding, prepared working directory, approved model/tool config, Stop Hook installation, and identity guards not supplied natively. Avoid two separate sources of conversation status. |
| `store.py` | SQLite for task registration, lifecycle, events, conversation associations, preparation/baseline/intelligence, validation attempts, artifacts, delivery states | **Split responsibility conceptually; defer database removal** | Mirrored conversation/event lifecycle is a reduction candidate. Durable validation reservation, attempt outcome, immutable SHA evidence, PASS-only acceptance and interruption reconciliation are safety-critical and POC4-proven; removing SQLite without equivalent atomic durable records would weaken the boundary. |
| `contracts.py` | Extensive typed task/lifecycle, policy and evidence contracts | **Narrow after consumer mapping** | Retain security policy, approved task/acceptance/baseline identity and immutable validation evidence. Native conversation states need not be redundantly modeled. Current delivery request requires `mode=none`; GitHub delivery is not implemented. |
| `preparation.py` | Credential-free, trusted repository mapping; exact baseline Git worktree preparation | **Keep** | Native local workspace alone does not establish trusted source/exact allowed commit, isolated worktree or acceptance identity. Same worktree should be shared by native agent, validator and delivery. |
| `baseline.py` | Deterministic Maven/build/OSV/constraints baseline with recorded evidence | **Keep** | Domain-specific evidence; no native alternative demonstrated. |
| `intelligence.py` | Optional pre-edit SBRI stage and durable intelligence evidence | **Keep optional; simplify wrapper only when justified** | Domain capability; not equivalent to general LLM reasoning or native UI. |
| `validation.py` | Independent deterministic Maven/OSV validation, classifications, bounded retries, workspace SHA binding and atomic verdict recording | **Keep** | POC2–4 establish native-hook bridge and that independent PASS must govern acceptance. Simplify only incidental orchestration, not validator isolation or acceptance rules. |
| `stop_hook.py` | Native command boundary for independent validator | **Keep thin** | SDK native Stop Hook invokes command, but hook failure can allow native finish. Durable PASS still gates acceptance/delivery. |
| Native Canvas/Server/SDK | Conversation execution, UI, events, Stop Hook invocation and model feedback | **Use directly** | Proven in native POC1–4; no benefit from duplicating generic lifecycle semantics in project code. |

This is a **static repository and committed-evidence review**, not a verified deletion dependency graph. The file `openhands_runtime.py` still states a 1.50.0 pin; the separately proven native test stack uses 1.55.1. Do not silently assume the older adapter already supports the new runtime.

## Minimal preservation invariants

1. Approved task objectives/policies, trusted repository source and exact baseline are immutable task inputs.
2. Agent, independent validator and eventual delivery operate against the **same** task Git worktree.
3. Agent cannot author or change the independent validator's verdict/evidence authority.
4. Native `finished`, Hook `ALLOW`, transport success and retries exhausted are **never** acceptance.
5. Accepted means **durable independent PASS**, with report identity, hash and validated Git state.
6. Interrupted or missing evidence never auto-converts to PASS; recovery does not invent a successful scan.
7. Failed validator tool calls are classified, not misreported as all vulnerabilities resolved.
8. Delivery is separately authorized from accepted verified content and must not trust native conversation state alone.
9. Frozen Gate-2 scripts/tag and original POC artifacts are untouched.

## Suggested implementation order (after review approval)

**A. Dependency/consumer inventory without modification.** Enumerate references to `TaskApi`, `SharedOpenHandsRuntime`, `SQLiteTaskStore`, event mirrors, and status contracts, including entrypoints and tests. Separate actual production consumers from compatibility test fixtures.

**B. Introduce one native-first thin execution path.** Use native 1.55.1 directly with the existing prepared workspace, baseline, optional intelligence, and independent Stop Hook; maintain durable task↔conversation/validation identity. Do not migrate everything at once.

**C. Demonstrate parity in a disposable test.** Native create/run/resume, immutable baseline, feedback loop, durable PASS/FAIL, interruption reconciliation, state mismatch rejection, and no acceptance on hook errors. Verify tests before deleting custom APIs or redundant lifecycle states.

**D. Retire redundant code only after proof.** Delete old HTTP conversation transport/task API/event mirrors if no legitimate consumers remain; retain a thin acceptance/evidence query interface only if an external integration requires one. Avoid porting generic task DB schemas to a new framework.

**E. Actual Maven/OSV plus agent-produced repair and exact-state PR delivery.** Separate follow-up tests, with explicit user approval before billable LLM execution.

## Explicitly not decided yet

- Whether a deployment genuinely needs a public task-registration HTTP API.
- Whether native persistence can replace *any* independent validation record while preserving atomicity and artifact identities.
- How native 1.55.1 exposes every requested task status to external automation clients.
- Isolation model for a production validator that an agent cannot tamper with.
- Production GitHub PR delivery and concrete cancellation/timeout behavior.
- Conclusive Agent Server process restart identity.
