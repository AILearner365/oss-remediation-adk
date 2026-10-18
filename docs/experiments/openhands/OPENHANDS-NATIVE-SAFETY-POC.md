# POC 4 — Native Stop Hook failure-mode safety

**Status:** harness and offline tests committed; no live runs completed yet.

## Purpose

Try to falsify the safety invariant:

> Native conversation `finished` and native Stop Hook `ALLOW`
> **do not** imply independently accepted remediation.
> Only a durable independent `PASS` may set `accepted=true`.

The harness reuses the POC3 prepared task fixture, actual
`SharedValidationService.handle_stop()`, actual SQLite store, and the
real OpenHands 1.55.1 Agent Server. It uses a **local mock LLM**.
No external model, real scanner, Maven build, PR, delivery, or frozen
Gate-2 modification occurs.

## Scenarios

| Case | Fault | Expected durable result | Native behavior being tested |
| --- | --- | --- | --- |
| `infrastructure` | `ValidationInfrastructureError` injected by runner | `INFRASTRUCTURE_FAILURE`, never accepted | Hook may allow terminal completion |
| `malformed` | Runner returns incomplete/contradictory report | `VALIDATOR_FAILURE`, never accepted | Hook may allow terminal completion |
| `exhausted` | Runner always returns unresolved target finding | Multiple `REMEDIATION_FAILURE`, never accepted | DENY while budget remains, terminal ALLOW after exhaustion |
| `hook-crash` | Stop Hook exits with code 37 before validator invocation | No durable PASS and never accepted | Observe how native HookExecutionEvent handles command error |

A native hook that exits abnormally **may fail open**. POC4 does not
try to override SDK behavior. An ALLOW or `finished` remains distinct
from acceptance. If a scenario cannot produce or retrieve the required
native evidence, its verdict is `NOT_PROVEN`, **not** `PASS`.

## Execute

Use the previously proven Canvas 1.27.1 + Agent Server/SDK 1.55.1
stack with constrained LiteLLM 1.105.1, still listening on port 8091.

First run the **offline** tests:

```bash
cd ~/oss-remediation-adk
git pull --ff-only origin openhands-service-integration
python3 -m unittest discover -s tests/integration -p 'test_openhands_native_safety_poc.py' -v
```

Then, **one native case at a time**; each gets its own new isolated fixture.
Start with the shortest, `infrastructure` case:

```bash
python3 scripts/openhands_native_safety_poc.py run --case infrastructure
python3 scripts/openhands_native_safety_poc.py publish --case infrastructure
```

Other cases **only after reviewing the preceding evidence**:

```bash
python3 scripts/openhands_native_safety_poc.py run --case malformed
python3 scripts/openhands_native_safety_poc.py publish --case malformed

python3 scripts/openhands_native_safety_poc.py run --case exhausted
python3 scripts/openhands_native_safety_poc.py publish --case exhausted

python3 scripts/openhands_native_safety_poc.py run --case hook-crash
python3 scripts/openhands_native_safety_poc.py publish --case hook-crash
```

If `run` exits nonzero, `publish` still records the result if the
sanitized report exists. **Do not delete fixture state and retry the
same case**: investigate the evidence, correct the harness, then use
a new case/version identifier. Previous POC1–3 fixtures are unchanged.

## What these results would and would not establish

These scenarios test the production validator **acceptance decision and
native invocation path**, with injected failures. They do not establish
real OSV/Maven timeout handling, a killed worker's recovery behavior,
or production delivery authorization. Those are separate tests before
production readiness.

Evidence from this harness is **not sufficient to remove durable
validation state, task identity records, or production controls**.
Removal/simplification decisions follow specific verified coverage.

The `hook-crash` case intentionally lacks an independent validation
result; this is a fail-open native execution experiment, **not** evidence
of successful remediation or permission to deliver.
