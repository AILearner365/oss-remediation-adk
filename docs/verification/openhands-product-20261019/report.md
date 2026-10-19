# OpenHands product implementation and review handoff

Implementation delivered on `openhands-service-integration`. Full paid remediation
and real GitHub delivery are **NOT YET VERIFIED**. No billable model run or target
repository mutation was authorized or performed during this implementation.

## A. Delivered architecture

One authenticated product API (`openhands_shared/server.py`) serves a small
submission/evidence UI and the thin HTTP CLI. `product.py` connects the existing
Git preparer, Maven/OSV assessor, optional SBRI assessor and native handoff.
The default target is pinned to `main-runrunning` at
`9ea1b0ed5ca255db0fc7c659d050896d3ed5db78`; preparation rechecks the remote SHA.

Native Canvas/Agent Server 1.55.1 owns the coding agent, conversation, tools,
Skills, events and Stop Hook invocation. The product records only task identity,
application stages, independent evidence and execution/delivery claims. It never
runs a second model loop or copies native event history into another ledger.

Submission prepares evidence and an idle native conversation. A separate exact
task/model/iteration authorization permits one durable `/run` claim. Independent
Maven/OSV validation and constraints remain authoritative. Native completion
cannot produce acceptance without PASS and a matching validated tree. Delivery
has a second authorization identifying the accepted base/tree/branch.

## B. Simplifications

- One supported startup reuses the published Canvas launcher and the same pinned
  uv environment for the product worker; package caches stay in `/tmp`, task and
  native state in persistent home. No startup smoke conversations or model calls.
- API, CLI and UI call one lifecycle. Operators no longer run preparation,
  baseline, SBRI, idle attachment, dispatch and finalization scripts in sequence.
- `python -m openhands_shared` now invokes the thin product client. The old
  registration-only server remains fixture support, not a competing product path.
- Existing SQLite transactions are retained for independent evidence and claims;
  one small application job table coordinates stages without duplicating native
  conversations/events. Product connections are explicitly closed.
- Delivery commits the exact accepted tree without changing the validated
  workspace. It supports accepted new/staged files and agent-made commits,
  removing the old POM-only delivery restriction without changing acceptance.

Prompts, remediation Skills, general engineering guidance and native coding-tool
configuration were preserved.

## C. Operator experience

```bash
python3 scripts/openhands_service.py start
python3 -m openhands_shared.cli submit docs/examples/real-app-remediation.json --idempotency-key my-task-001
python3 -m openhands_shared.cli list
python3 -m openhands_shared.cli status TASK_ID
python3 -m openhands_shared.cli result TASK_ID
python3 scripts/openhands_service.py restart
```

UI: Cloud Shell preview port 8080; native Canvas: port 8091. Authenticate using
`~/.openhands/oss-remediation/product/api-key.txt`, select a durable task, and
inspect its native activity, reports and diff. The example payload targets the
approved real repository/branch/SHA, enables SBRI and requests draft delivery
intent. It does not grant model or GitHub mutation authorization.

The [operator guide](../../openhands-product-operations.md) includes the exact
REST request, configuration, authorization payloads, credential prerequisites,
storage paths and recovery commands. Public inputs contain no implementation
paths, worker IDs, hook commands or generated conversation IDs.

## D. Acceptance evidence

| Journey | Result | Evidence and limits |
| --- | --- | --- |
| Fresh native package installation/startup | PASS | Published Canvas 1.27.1, Server/SDK/tools 1.55.1, LiteLLM 1.105.1 installed/reused; API and both UIs served HTTP 200. No smoke or model dispatch. |
| Real-app API submission | PASS | HTTP 202; task `task_0aea86cbafcb458981034d71626a77d9`. One shared lifecycle performed all deterministic stages and native idle attachment. |
| Real Maven baseline | PASS | `mvn -B -ntp clean verify`: all four modules SUCCESS; 4 tests, zero failures/errors/skips; `BUILD SUCCESS`, total time `01:36 min`. |
| Real OSV baseline | PASS | Fresh scanner 2.6.0 result: 50 original findings. Report SHA256 `0da60ebe251e975b3f053de188637965b6ba382cb4a0615fbd9275dcbe0f3e5c`. |
| Real SBRI | PASS | COMPLETE; evaluated 4.0.6, 4.0.7, 4.0.8. These are intelligence, not prescribed upgrades or compatibility acceptance. |
| Native handoff | PASS, idle integration | Conversation `df6ed4e1-7f29-41a0-87b6-e1e36b0070f0`; correct isolated workspace, approved two Skills, terminal/file-editor/task-tracker tools, guidance, SBRI context, exact persisted Stop Hook, model and 12-iteration budget verified. No `/run`. |
| Independent acceptance and feedback | Offline PASS; real run NOT YET VERIFIED | Fake build/scan/native transport journeys exercise PASS, denial feedback, bounded failure, mutated-tree rejection and retained reports. The real task has zero validation attempts because no model was authorized. |
| CLI | PASS | Real `status` returned the persistent task and idle native conversation with exit code 0. CLI regression also runs through the same HTTP backend. |
| Browser UI | PASS | Chromium offline submission/authorization/activity journey passed. Live browser retrieved real baseline evidence with zero JavaScript errors, before and after restart. Native Canvas conversation rendered HTTP 200 with zero observed JavaScript/API errors. |
| Restart/recovery | PASS for service/idle state and offline failure scenarios | Supported `restart` returned PRODUCT_RUNNING; same task, baseline, SBRI and native conversation recovered. Zero execution claims, zero model runs. Unknown dispatch responses never replay `/run`; unclaimed authorizations are gated on restart. |
| Draft-PR delivery | Offline PASS; live NOT YET VERIFIED | Local Git and fake GitHub tests cover lost push response, lost PR creation response, service reopening, one commit/branch/PR, mismatched remote rejection and unchanged base/workspace. No target-repository push or real PR. |

The focused regression command selected product, native handoff/stable hook,
shared preparation/baseline/intelligence/validation, startup, delivery/ledger and
metadata API suites:

```text
Ran 97 tests in 70.108s
OK
```

After the final connection, credential, accepted-tree and capacity changes, the
affected product/startup/delivery suites passed again, including the added
agent-commit and low-storage authorization cases. These overlap the regression
suite; do not sum them as unique tests:

```text
Ran 21 tests in 19.823s
OK

Ran 1 test in 14.659s
OK
```

The one-test command is the optional offline Chromium journey. Playwright 1.56.1
and Chromium were installed under `/tmp` for testing only; they are not product
runtime dependencies. Run it with `PLAYWRIGHT_MODULE`, `PLAYWRIGHT_NODE` and
`PLAYWRIGHT_BROWSERS_PATH` pointing at that temporary install:

```bash
python3 -m unittest tests.integration.test_openhands_product_browser.BrowserJourney -q
```

Python compilation and `git diff --check` also passed. Detailed outputs:
[regression](focused-tests.log), [final changes](final-change-tests.log),
[offline browser](browser-offline-tests.log), [live browser](browser-live.json),
[restart](restart.log), [native/task evidence](real-app-task.json).

Durable raw evidence remains under
`~/.openhands/oss-remediation/product/artifacts/task_0aea86cbafcb458981034d71626a77d9/`.
The Maven output is in `baseline/runtime/artifacts/commands/`; the immutable
baseline report and SBRI artifacts are retrievable through the supported API/CLI/UI.
Local screenshots are `/tmp/codex-work-cache/openhands-product-ui-after-restart.png`
and `/tmp/codex-work-cache/openhands-native-canvas.png`.

The previous failure was an unfinished browser timeout, not a persistent CLI
status failure. The UI now refreshes the selected task as its phase changes;
browser launch and action timeouts are explicit. Both browser paths subsequently
passed. Startup also fixes the transient launcher PID handoff and records native
ownership before readiness, making a partially successful spawn recognizable.

Legacy task `task_943461f6ed864a2baf96642c61746bd0` was inspected: its database is
intact and execution is NOT_STARTED. Its old native conversation returns 404 on
the recovered server. Its immutable contract and evidence were preserved; no
expired hook was waived or redispatched. The new isolated task above was created
through the supported API, rather than reconstructing the experimental chain.
See [legacy inspection](legacy-inspection.json).

## E. Remaining issues and external gates

1. Paid autonomous remediation of this selected task is **NOT YET VERIFIED** and
   remains prohibited without separate authorization. The real task is ready at
   AWAITING_EXECUTION_AUTHORIZATION; no final remediation acceptance is claimed.
2. Real independent Stop Hook execution/feedback and an agent-produced accepted
   multi-module change require that run. Offline evidence cannot establish them.
3. Real target-repository GitHub mutation is **NOT YET VERIFIED** and requires
   separate authorization after independent acceptance, plus GitHub API and Git
   HTTPS push credentials. No target PR URL exists.
4. Current Cloud Shell persistent home has about 93 MiB free, below the 256 MiB
   preparation/dispatch guard. Existing task observation works, but free additional
   capacity before submitting another preparation or authorizing the selected run.
   Product state uses about 68 MiB; unrelated user data and caches were preserved.

Operational limits: this is a trusted local Cloud Shell runner; iteration/denial
bounds are not a hard dollar cap or a host sandbox. A partially completed build,
scan or context operation without enough committed evidence stays recovery
required for inspection. A missing native conversation or obsolete persisted hook
is not silently replaced. Home storage is finite: preparation checks 256 MiB
headroom, Maven is given a 512 MiB heap, but there is no automatic evidence
deletion or hard filesystem quota. Long-term evidence retention is an operator
responsibility. Authorization reports `INSUFFICIENT_STORAGE` without claiming or
dispatching a model when home is too full. A full VM replacement was not exercised; package reinstall and
native persistence were tested separately through installation and service restart.

## F. Integration GitHub delivery

Repository: `https://github.com/AILearner365/oss-remediation-adk.git`.
Branch: `openhands-service-integration`. The implementation and this evidence are
committed together; the completion response records the final commit and remote
SHA verification. Historical/frozen branches and the target application's base
branch were not modified.

The exact [changed-file list](files-changed.txt) accompanies this report.

Changed areas: supported startup/native handoff; product API/lifecycle/CLI/UI;
deterministic tool environments and validation report serialization; exact-tree
delivery/recovery; focused and browser tests; operator guide/example/evidence.

## G. Review handoff

Start with `openhands_shared/product.py`, `server.py`, `cli.py`, `ui.html` and
`scripts/openhands_service.py`. Native request/dispatch checks live in
`scripts/openhands_native_remediation.py`; authoritative validation remains in
`openhands_shared/validation.py`, `stop_hook.py`, `store.py` and the existing
deterministic validator. Review `scripts/openhands_pr_delivery.py` for durable
commit intent, create-only remote branch lease, PR reconciliation and exact
accepted-tree binding.

Use `tests/integration/test_openhands_product.py` to trace submission through
native handoff, authorization, independent verdicts, results, restart and delivery
failure recovery. Browser journeys use the same API, not a UI execution path.
Native API/UI integration is verified through the actual idle real-app
conversation; full paid execution is explicitly still gated. Resume observation
using `list`/UI, not historical experimental drivers. The exact remaining gates
are the external checks and capacity requirement in section E; do not recreate the task or start
another model run merely because an HTTP response is uncertain.
