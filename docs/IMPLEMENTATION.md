# Stage B implementation and proof

Implemented against `PRODUCT-CONTRACT.md` and `ENGINEERING-HANDOFF.md`, starting
at `4dcc2fe79d6dc04fc1a3bab6cda2a79301d56b25` on `openhands-native-product`.
No blanket import of the experimental source tree. Existing untracked artifacts
left by branch switches are ignored and preserved, not product dependencies.

| Contract responsibility | Implementation | Verification |
| --- | --- | --- |
| Approved inputs, isolated baseline | `contract.py`, `repository.py`, `runtime.prepare_task` | Offline task rejection, real local Git snapshots/exports and tree binding |
| One native reasoning/coding agent | `native.py`, `runtime.attach/dispatch` | Installed 1.55.1 creation/HookConfig schema; offline idle-message-before-verification and one-shot run claims |
| Discovery, alternatives, intent/outcome, reassessment | Native AgentContext instructions, `journal.py`, native tools | Offline pre-edit intent, exact-tree outcome, failed-cycle feedback and bounded recovery checks; reasoning quality needs a real task |
| Resolved Maven dependencies/build/test evidence | `validation.evaluate/resolved_inventory` | Real Git export, controlled offline Maven/OSV process outputs; active-reactor and package-coverage guards |
| Trusted final acceptance | `validation.compare`, `runtime.hook` | PASS/FAIL/INCONCLUSIVE, aliases/new findings, tests/properties/version/path constraints, no delivery on non-PASS |
| Draft delivery after exact-tree PASS | `delivery.py` | Real local commit-tree checks and offline remote-boundary doubles for reconciliation, drift and uncertain-POST refusal |
| No alternate lifecycle engine | Small private JSON/locks; native history/API; CLI commands exit | No product service, SQLite, watcher, custom model tool loop or second agent |

## Proven / partial / not proven

| Capability | Status | Evidence / limit |
| --- | --- | --- |
| Native Gemini -> Stop -> independent tree-bound PASS -> draft PR | **PROVEN (prior one-file smoke)** | [PR #214](https://github.com/AILearner365/maven-multimodule-app/pull/214); conversation `05f7716a-90bc-4ec5-a90e-01b7a4de5fa0`; [sanitized evidence at f72e5308](https://github.com/AILearner365/oss-remediation-adk/blob/f72e5308704960ee911f382f96bf0b7948435216/docs/experiments/openhands/evidence/native-wiring-20261019.json) |
| New product request follows actual native extension contracts | **PROVEN offline** | Parsed with installed Server/SDK 1.55.1, no API submission/model execution |
| Deterministic safety boundaries and recovery | **PARTIAL** | Offline Git tests and controlled process/remote doubles; no production crash/isolation proof |
| New Maven/OSV validator inside native Stop on a real repository | **NOT PROVEN live** | New validator uses resolved graphs and OSV 2.6.0, not the smoke file whitelist; real baseline and candidate execution still required |
| Whole-goal autonomous remediation/reasoning quality | **NOT PROVEN** | Native operating instructions and bounded records implemented; no real remediation run authorized yet |
| Optional SBRI/research | **PARTIAL** | Existing installed helper references can be supplied; optional native-shell capabilities, no mandatory SBRI stage; not live exercised here |
| Persistent ADC and secure multi-user isolation | **NOT PROVEN** | Exact-runtime ADC preflight implemented; credential persistence and OS sandbox are deployment responsibilities |
| Canvas conversation browser activity | **NOT PROVEN** | Prior API visibility succeeded; fresh browser showed onboarding |

## Source extraction and installed conventions

Git tree capture, private claims, create-only push and exact-draft reconciliation
derive from the proven `openhands_native_wiring_hook.py`/delivery helpers at
`f72e5308`. The request, `run:false` initialization ordering and native model retry
settings derive from its submitter. No experimental product-store import remains.
Maven/OSV coverage failure classifications and evidence-before-acceptance were
reviewed in the historical deterministic scanner/validator. The old native smoke
whitelist and terminal-only three-iteration budget were not generalized into a
permissive validator or retained as product defaults.

Installed sources checked: `agent_server.models.StartConversationRequest`,
`event_service` passing `hook_config` into `LocalConversation`, lazy hook setup,
`HookConfig.stop`/command definitions, Stop blocking semantics, and
`AgentContext.system_message_suffix`. Prompt extensions and terminal/file editor/
task tracker use native conventions. Hook processing remains inside OpenHands.

## Offline checks

```bash
python3 -S -m unittest discover -s tests_native -v
# Use the exact installed native Python for the optional real schema check:
<native-server-python> -m unittest discover -s tests_native -p test_sdk_contract.py -v
python3 -S -m native_remediation check-task --task examples/maven-task.json
python3 -S -m compileall -q native_remediation tests_native
git diff --check
```

The offline Maven process and GitHub/native server test doubles are explicitly
test boundaries, **not successful end-to-end remediation evidence**. They perform
no network, model, target-repository build or PR operations. Product code does not
use them. No model or remediation PR was created during implementation.

Recorded verification: 21 tests passed under the installed native 1.55.1 Python,
including its actual creation/hook schema. The stdlib-only run passed 20 tests
and skipped only that optional installed-SDK test. Example task validation,
Python syntax checks and staged whitespace/credential checks also passed.

Next single step: review the concrete task JSON against a freshly approved base,
then authorize `prepare` to produce the first product Maven/OSV baseline (no model).
Resolve any real coverage/toolchain blocker before authorizing one native run.
