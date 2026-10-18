# Native-first remediation integration: first implementation slice

**Date:** 2026-10-18  
**Status:** non-executing handoff code committed; offline test pending Cloud Shell.

## Goal

Native Canvas/Agent Server/SDK provides UI, conversation lifecycle, execution, native Stop Hook and feedback. Existing deterministic Git preparation, baseline, optional Spring Boot release intelligence and Maven/OSV validation remain domain-specific. There is **no new custom task HTTP API, LLM loop, event mirror or database** in this new slice.

`scripts/openhands_native_remediation.py` is a **read-only handoff builder** from existing durable task records to the official OpenHands Agent Server conversation create payload. It deliberately does not yet call native POST/create or `/run`, because the current records were provisioned using the legacy 1.50.0 adapter and a validated migration from them to the 1.55.1-native runtime is outstanding.

It requires:

- existing task `AGENT_RUNNING`, not accepted;
- exact prepared Git worktree and baseline;
- a persisted task-to-conversation ID and recorded dispatch claim;
- a compatible credential-free, approved Stop Hook configuration referring to the same durable SQLite database;
- the official native request's `worktree=false` so it uses **exactly that worktree**, not another checkout;
- native Stop Hook command pointing to `openhands_shared.stop_hook`, using explicit module import root so task working directory does not affect execution.

`validate_native_response()` checks conversation ID, `idle`, prepared workspace and persisted Stop Hook before execution. The safe CLI prints an allowlisted summary rather than LLM credentials.

## Offline verification

```bash
cd ~/oss-remediation-adk
git pull --ff-only origin openhands-service-integration
python3 -m unittest discover -s tests/integration -p 'test_openhands_native_remediation.py' -v
```

No paid LLM, network calls, scanner or modification to frozen Gate-2.

## Next narrow implementation slice

1. Add a native conversation **idle-create** action, using the existing Agent Server 1.55.1 API, with strict response verification and no automatic `/run`. Test with the local mock credentials from POC 3.
2. Replace legacy 1.50.0 runtime provisioning/dispatch *for new tasks* with a small verified native binding; avoid duplicating event history or custom API. Keep the independent PASS-only acceptance store until parity is demonstrated.
3. Integrate an agent-produced local fixture change and actual validation outcome using native Stop Hook.
4. Real Maven/OSV vulnerability remediation with explicit user approval for billable model execution, then GitHub PR delivery of exact validated state.

POC4 evidence supports native Stop Hook failure handling and non-acceptance without PASS, **not** real scanner/PR readiness. Agent completion or native Hook ALLOW cannot authorize delivery.
