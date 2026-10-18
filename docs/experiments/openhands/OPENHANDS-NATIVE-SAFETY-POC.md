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

## Interrupted validator attempt and native restart recovery

This is a **two-stage native test**, separate from the four completed cases.

The first native Stop Hook durably reserves attempt 1 in the existing
SQLiteTaskStore, then exits with code 37 *before* any validation report is
written. Native OpenHands may finish despite the hook error. The test
requires the task to remain unaccepted and attempt 1 to remain `RUNNING`.

After the native stack restarts, stage two reuses **the same persisted native
conversation, task ID, worktree and baseline**. The next real native Stop Hook
invocation calls the existing `SharedValidationService.handle_stop()`.
The store reuses the original `RUNNING` attempt; the service records
`VALIDATOR_FAILURE` for the missing immutable report, **without calling the
validator runner again**. The result must remain unaccepted even if the
native conversation finishes.

This injects a **hook-command exit** at the durable reservation boundary;
it does **not** simulate a genuine OS kill or interrupt real Maven/OSV work.

First run offline tests, then the start phase:

```bash
cd ~/oss-remediation-adk
git pull --ff-only origin openhands-service-integration
python3 -m unittest discover -s tests/integration -p 'test_openhands_native_recovery_poc.py' -v
python3 scripts/openhands_native_recovery_poc.py start
```

Only if `start` reports PASS, restart the **owned** 1.55.1 stack using
the existing safe scripts. POC1's normal/remediation conversation state
and previous evidence are preserved.

```bash
python3 scripts/openhands_native_poc.py stop --server-version 1.55.1
python3 scripts/openhands_native_poc.py run --server-version 1.55.1
```

Then explicitly attempt native recovery of the same conversation:

```bash
python3 scripts/openhands_native_recovery_poc.py recover
python3 scripts/openhands_native_recovery_poc.py publish
```

The recovery harness checks that the launcher PID differs from the
start stage's PID. It uses a fresh fixture at
`/tmp/openhands-native-poc-1271-server-1551/hook-poc4-recovery-restart-v2`.
If the same-conversation continuation API does not support this
sequence, the result is NOT_PROVEN; investigate native events instead
of claiming recovery.

The recovered report is
`~/openhands-native-poc-reports/native-recovery-poc4-restart-v2.json`.
No previous POC evidence is overwritten. It is not a delivery or
security remediation acceptance test.

## Restart-v1 diagnostic and correction (2026-10-18)

The initial native start stage was **NOT_PROVEN**. It produced five
`HookExecutionEvent` records, each exit code 2 / blocked true, but the
task store contained **zero** validation attempts. Root cause: the
POC recovery script's `argparse` accepted only `start`, `recover`,
`publish`; the native hook called the missing `hook` subcommand.
Argument parsing exited 2 before `begin_validation()`.

Correction: explicitly dispatch `hook`, add an offline CLI-dispatch
regression test, and use fresh **restart-v2** state. The restart-v1
conversation and its start-report are preserved. Exit code 2 does not
prove independent validation denial unless a durable attempt corroborates
it. Run offline tests and **only the start stage first**; review its
snapshot before attempting a server restart.
