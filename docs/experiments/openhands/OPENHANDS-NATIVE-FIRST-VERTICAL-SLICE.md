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

## Native idle-create extension (2026-10-18)

`create_idle_native_conversation()` invokes only the native Agent Server
`POST /api/conversations?include_skills=true` and
`GET /api/conversations/{id}?include_skills=true`. It requires exact
conversation identity, `idle` execution status, matching existing prepared
workspace and persisted independent Stop Hook. It never sends a user message or
calls `/run`.

Two offline HTTP-mock tests cover endpoint ordering, success and rejection of
a missing persisted hook. Smoke runner
`scripts/openhands_native_idle_create_poc.py` creates a fresh disposable
existing-service fixture and a native **idle** conversation on 1.55.1, using a
local-only mock LLM URL and dummy key. The mock model server need not run:
there are **zero model requests**.

```bash
cd ~/oss-remediation-adk
git pull --ff-only origin openhands-service-integration
python3 -m unittest discover -s tests/integration -p 'test_openhands_native_remediation.py' -v
python3 scripts/openhands_native_idle_create_poc.py
```

Smoke report: `~/openhands-native-poc-reports/native-idle-create-v1.json`.
No previous fixtures are overwritten. Do **not** execute that conversation:
its data records remain synthetic and the real scanner configuration is not
installed.

This checks native conversation creation but does **not** yet remove the legacy
provisioning records used solely by the fixture setup. The next work is to
replace that prerequisite cleanly for new tasks before removing the older
runtime adapter.

## Idle create v1 failure and v2 correction

Offline handoff tests: 7 passed. Live idle-create v1 failed at native
`POST /api/conversations` with HTTP 422 and error
`loc=["body","tags"], type=value_error`. Native OpenHands conversation
tags require lowercase alphanumeric keys; the bridge sent `taskId`.
The v2 correction uses `taskid`, adds an offline key-format regression
assertion, and uses fresh disposable `native-idle-create-v2` state.
Retain v1 failure evidence; do not overwrite it. No model execution occurred.

Run the same commands with the updated branch:
```bash
cd ~/oss-remediation-adk
git pull --ff-only origin openhands-service-integration
python3 -m unittest discover -s tests/integration -p 'test_openhands_native_remediation.py' -v
python3 scripts/openhands_native_idle_create_poc.py
```
Expected report: `~/openhands-native-poc-reports/native-idle-create-v2.json`.
