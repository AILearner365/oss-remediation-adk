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

## Native idle-create v2 initialization discovery and v3 correction

A user read-only GET demonstrated that POC3 had a Stop Hook, while
new native-idle-create-v2 immediately after POST had `hook_config=null`.
Attaching one initial user message using native `POST /events` with
`run=false` made `hook_config` appear while conversation remained `idle`.
The create-only helper now follows the observed native initialization
sequence: **POST conversation → POST initial user event with run=false →
GET persisted conversation → verify exact hook, workspace, ID and idle state**.
There is still no `/run` and no LLM request.

V2 state is retained; v3 uses a fresh isolated task fixture.
The offline tests assert exact call ordering, `run=false`, and rejection
when the native server fails to persist the Stop Hook.

```bash
cd ~/oss-remediation-adk
git pull --ff-only origin openhands-service-integration
python3 -m unittest discover -s tests/integration -p 'test_openhands_native_remediation.py' -v
python3 scripts/openhands_native_idle_create_poc.py
```

Expected report: `~/openhands-native-poc-reports/native-idle-create-v3.json`.

## Native-first provisioning without legacy runtime dispatch (v4)

The v3 live smoke passed native idle creation, Stop Hook persistence and
identity checks. The new v4 fixture uses the existing deterministic task
preparation/baseline/intelligence and SQLite runtime identity contract, but
**does not** call the 1.50.0 legacy adapter's `provision()` or
`start_execution()`. It records a `CONVERSATION_READY / NOT_STARTED`
native identity, creates and initializes the OpenHands 1.55.1 conversation
using native API endpoints with `run=false`, verifies Stop Hook and workspace,
and links the unique native initial `MessageEvent` as
`CONTEXT_ATTACHED`. No execution claim is created.

A new offline test asserts that a not-started native identity can construct
the handoff without a dispatch claim and that inconsistent context states
are rejected. A successful smoke demonstrates removal of the **fixture**
legacy provisioning dependency; it does not yet prove production end-to-end
real Maven/OSV remediation or native execution safety. v1-v3 are preserved.

```bash
cd ~/oss-remediation-adk
git pull --ff-only origin openhands-service-integration
python3 -m unittest discover -s tests/integration -p 'test_openhands_native_remediation.py' -v
python3 scripts/openhands_native_idle_create_poc.py
```

Expected v4 report: `~/openhands-native-poc-reports/native-idle-create-v4.json`.
No model requests are sent.

## Native one-shot dispatch guard (offline tests first)

`dispatch_native_once()` now uses native Agent Server endpoints for one
`/run` dispatch, with no custom conversation API. Preconditions are durable
`CONTEXT_ATTACHED` identity and an independent Stop Hook verified via native
GET while `idle`. It records `claim_execution` **before** native POST
`/run` and then marks `DISPATCHED` only after a successful response or
observable native `running/finished` state.

A second call with the same dispatched claim returns `ALREADY_DISPATCHED`
without sending `/run`. Lost POST responses are reconciled by native GET.
When the POST outcome cannot be proven, the durable claim transitions to
`RECOVERY_REQUIRED`, and later calls cannot resend `/run` automatically.
The same fail-closed rule applies to an existing unconfirmed intent.
The native `finished` state alone never implies security acceptance.

Two new offline tests simulate normal dispatch and an ambiguous connection
loss, enforcing only one POST and no duplicate dispatch.

**Scope restriction:** do not invoke this against v4's existing idle conversation.
Its Stop Hook uses the real validation CLI with a synthetic task fixture;
executing it would not constitute a valid real Maven/OSV experiment. A
separate fixture with explicitly synthetic Stop Hook and local-only MockLLM
will be needed for the next live /run test. No paid model call is authorized.

## Native-first execution + synthetic Stop Hook live test (v1)

`scripts/openhands_native_execution_poc.py` runs a fresh disposable
`native-execution-v1` task and native 1.55.1 conversation. It uses the
previously proven direct-native fixture (`CONVERSATION_READY`, no legacy
adapter), calls native `POST /run` using `dispatch_native_once()` with an
existing SQLite execution intent, and requests a duplicate dispatch to prove
it does **not** call `/run` a second time.

A loopback-only HTTP mock advertises the SDK FinishTool. A **synthetic**
native Stop Hook invokes `SharedValidationService` with `ArtifactRunner`,
which checks a disposable marker, **never** Maven/OSV. On first independent
FAIL, native Stop Hook must DENY. The *test coordinator*, not the agent,
creates the repair marker only after verifying the native DENY event and first
durable REMEDIATION_FAILURE. The subsequent mock Finish must receive the
failed-validation feedback and produce a durable PASS before security
acceptance. Results distinguish synthetic coordinator repair from real
agent-generated edits.

```bash
cd ~/oss-remediation-adk
git pull --ff-only origin openhands-service-integration
python3 -m unittest discover -s tests/integration -p 'test_openhands_native_remediation.py' -v
python3 scripts/openhands_native_execution_poc.py run
```

The smoke runs the **native agent with a local mock model** and invokes an
explicitly synthetic validator; no paid LLM, Maven, OSV or GitHub delivery.
The report is in
`~/openhands-native-poc-reports/native-execution-v1.json`. Do not
re-run an already attempted v1 fixture, and preserve it on any failure.
A passing test is not evidence of agent-written Maven vulnerability repairs.

## Native execution v1 result and exact-marker correction

Cloud Shell v1: 10 offline tests PASS; live verdict **NOT_PROVEN**.
Native finished, exactly one /run, repeat dispatch ALREADY_DISPATCHED,
four native Stop Hook events and four model requests, with independent
outcomes REMEDIATION_FAILURE x4. The coordinator repaired the fixture after
verified DENY and the mock model saw feedback, but the validator never
observed the expected exact marker. Consequently there was no false
independent acceptance.

Root cause: the existing synthetic ArtifactRunner requires the literal
two bytes `\\` + `n` at the end of its marker, while the new execution
coordinator wrote an actual newline. Both now use one shared
`REPAIR_BYTES` constant. Offline regression asserts that matching bytes
yield PASS while a newline yields FAIL. Previous v1 state/report are
preserved; next live scenario is `native-execution-v2`.

```bash
cd ~/oss-remediation-adk
git pull --ff-only origin openhands-service-integration
python3 -m unittest discover -s tests/integration -p 'test_openhands_native_remediation.py' -v
python3 scripts/openhands_native_execution_poc.py run
```

A v2 PASS demonstrates native synthetic feedback and validator-authorized
acceptance; it does not demonstrate autonomous agent-made remediation.

## First real Maven/OSV remediation gate: preparation (not execution)

The Cloud Shell user reported `native-execution-v2` PASS and 11/11
offline tests. A limited, explicitly user-reported summary is committed at
`docs/experiments/openhands/evidence/native-execution-v2-user-verified-20261018.json`.
The raw report remains on Cloud Shell and has not been independently uploaded.
The synthetic test used a coordinator-applied repair; it is not evidence of
autonomous vulnerability remediation.

The first *real* test must start with an independently reproducible,
**disposable** Maven repository, a clean exact Git commit, a known vulnerable
dependency/finding, a trusted approved OSV scanner binary, and a validator
configuration that matches the task acceptance criteria. Do not use a
production repository as the first scenario. The existing
`ExistingDeterministicBaselineRunner` and
`ExistingDeterministicValidationRunner` must run the real Maven build and
OSV scanner; neither the synthetic ArtifactRunner nor a mock repair marker
is sufficient for this acceptance gate.

A read-only preflight script now checks basic prerequisites without editing
or scanning the repository:
```bash
cd ~/oss-remediation-adk
git pull --ff-only origin openhands-service-integration
python3 -m unittest discover -s tests/integration -p 'test_openhands_real_remediation_preflight.py' -v
python3 scripts/openhands_real_remediation_preflight.py \
  --repository /absolute/path/to/disposable-maven-repo \
  --scanner /absolute/path/to/approved/osv-scanner
```

`READY_FOR_BASELINE_SETUP` means only: clean Git root and pom.xml present,
Maven responds to `-version`, and the explicitly supplied scanner binary
responds to `--version`. It is **not** a vulnerability baseline, scanner
approval, complete validation setup, or authorization to run an agent.
No scanner scan, Maven goal, dependency download or model call occurs.
A missing scanner or repository blocks progress rather than being guessed.

After preflight: capture the exact commit and scanner identity; run Maven build
and a real OSV baseline using the existing deterministic services; record
target advisory identities and a verified fixed-version candidate; confirm
that a deterministic fixed version builds and reduces target findings.
Then assemble an agent task/instruction from that authoritative baseline
and invoke native OpenHands with durable dispatch + independent real Stop Hook.
Obtain **explicit authorization before any paid model execution**. Finish with
full independent validation, exact workspace state binding and only then
possible safe delivery. The agent's native `finished` event is never PASS.

Current status: real Maven/OSV preflight code committed; no real baseline,
model execution, scanner output or GitHub PR has been claimed.
