# POC 2: Native OpenHands Stop Hook execution (1.55.1)

**Status: implementation committed, Cloud Shell execution pending.** This is a
minimal **integration experiment**, not a real vulnerability remediation run.

## Objective

Prove that Agent Server/SDK **1.55.1**, with Canvas **1.27.1**, can
execute a genuine native Stop Hook when the agent attempts to finish; propagate
a DENY to the same agent; expose the denial in native events and a subsequent
LLM request; retry and eventually complete after a synthetic PASS.

The local mock model responds using an OpenAI-compatible
`/v1/chat/completions` endpoint bound to loopback `127.0.0.1:12997`. It
attempts the SDK-advertised FinishTool, not textual claims of completion.

A separate conversation and work directory under
`/tmp/openhands-native-poc-1271-server-1551/hook-poc2` isolate this test from
the normal and remediation conversations created by POC1. This fixture does
**not** use the real OSV/Maven independent validator; a fake verdict advances
from DENY to ALLOW after one actual hook invocation.

## First run on Cloud Shell

Run from the integration branch with the 1.55.1 Canvas/Agent Server stack
already running (via `openhands_native_poc.py run --server-version 1.55.1`):

```bash
cd ~/oss-remediation-adk
git pull --ff-only origin openhands-service-integration
python3 -m unittest discover -s tests/integration -p 'test_openhands_native_hook_poc.py' -v
python3 scripts/openhands_native_hook_poc.py run
python3 scripts/openhands_native_hook_poc.py publish
```

**Important:** The POC2 `run` command starts a *real agent run* but sends requests
only to a local mock endpoint. It does **not** invoke Vertex/Gemini or ask an agent
to edit a real repository. It does not change the POC1 conversation IDs.

On failure, publish the report if present, and inspect the disposable logs;
do not run again against the same fixture without diagnosis, since the
evidence is deliberately retained and the runner refuses to overwrite it.
Do not publish raw logs, hook stdin or model requests.

## Acceptance contract

A PASS requires ALL of:

1. Native Stop Hook actually invoked twice or more.
2. Native `HookExecutionEvent` records observed for STOP.
3. The first native hook event was `blocked=true` and fixture DENY.
4. A subsequent local model request includes the exact injected DENY marker.
5. A later native Stop Hook event reports allow and synthetic fixture PASS.
6. The native conversation reaches `finished` in the same conversation.

The report is saved in
`~/openhands-native-poc-reports/native-hook-poc-1.55.1.json`.
`publish` commits a **sanitized** copy under
`docs/experiments/openhands/evidence/native-hook-*.json`.
The script exits nonzero if acceptance is not proven. Test failure is diagnostic
evidence; do **not** treat it as a reason to change the remediation architecture
until actual events and errors are investigated.

## Important limits

The mock fixture transitions to PASS after an initial native hook invocation.
This proves wiring and feedback **only**. It does **not** prove that a real
Maven/OSV validator correctly classifies findings, that error paths remain
fail-closed, that a malicious agent cannot interfere with validation state,
that delivery is safe, or that crash recovery handles in-flight remediation.
Those require separate deterministic checks. Native `finished` alone is
never accepted as a security-validation PASS.

The existing 1.55.1 stack normally serves Canvas on Web Preview port **8091**.
POC2 is controlled from the terminal; browser viewing is optional.
Use `scripts/openhands_native_poc.py stop --server-version 1.55.1` to stop
the full-stack launcher after the test.
