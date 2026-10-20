# Autonomous OSS Vulnerability Remediation

OpenHands is the native autonomous agent framework, not the product identity.
Development branch: `autonomous-oss-remediation`; the previous
`openhands-native-product` branch is preserved at `11431b428a69f4525679bda5880bf0a0d05137bc`.

**Status: native pre-inference preparation migration is BLOCKED.** Installed
OpenHands 1.55.1 does not establish all required failure, recovery and trust
guarantees through the reviewed supported facilities. See the
[exact source/API evidence](docs/NATIVE-PREPARATION-BLOCKER.md).
The existing Maven/OSV validator, native agent/Stop integration, bounded records
and exact-tree draft delivery remain preserved as diagnostic implementation work.
The external prepare/attach/run sequence is not a compliant normal product flow.
No wrapper, custom service, SDK patch or orchestration engine was added.

Read [operations and commands](docs/OPERATIONS.md) and the
[requirement mapping / proof table](docs/IMPLEMENTATION.md).
The governing requirements remain [PRODUCT-CONTRACT.md](PRODUCT-CONTRACT.md) and
[ENGINEERING-HANDOFF.md](ENGINEERING-HANDOFF.md). Offline safety checks pass, but
do not prove the missing lifecycle contract or real Maven/OSV remediation under
the native hook.

The parent commit `f72e5308704960ee911f382f96bf0b7948435216` retains the verified native OpenHands smoke and historical experiment repository **for reference only**. The product branch's tree starts clean by design: do not merge the experimental tree back wholesale.

Goal: an autonomous, evidence-driven Java Maven OSS remediation workflow, executed by native OpenHands and gated by independent deterministic validation before GitHub draft-PR delivery. Preserve native API/SDK/Canvas and built-in hook semantics, not an invented service/API/UI/database.

Offline entry commands (no model or external mutation):

```bash
python3 -S -m native_remediation check-task --task examples/maven-task.json
python3 -S -m unittest discover -s tests_native -v
```

The `native_remediation` import path, `oss-remediate` diagnostic CLI and existing
delivery-branch naming remain compatible with stored hooks/claims. `prepare`,
`attach`, `run` and `resume` are preserved diagnostics, not the required native
preparation integration. No example, test pass or prior smoke authorizes a model
call or target PR. Do not launch normal product execution while the gate is blocked.
