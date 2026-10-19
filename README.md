# Native OpenHands OSS Remediation Product

This is the clean product working tree. Stage B implementation is available as
`python3 -m native_remediation`: approved-revision preparation, deterministic
Maven/OSV baseline and acceptance, one native OpenHands agent, bounded cycle
evidence, and PASS-only draft delivery. No product server, UI or database.

Read [operations and commands](docs/OPERATIONS.md) and the
[requirement mapping / proof table](docs/IMPLEMENTATION.md).
The governing requirements remain [PRODUCT-CONTRACT.md](PRODUCT-CONTRACT.md) and
[ENGINEERING-HANDOFF.md](ENGINEERING-HANDOFF.md). The product is offline-verified;
real Maven/OSV remediation under the native hook is **not yet live-proven**.

The parent commit `f72e5308704960ee911f382f96bf0b7948435216` retains the verified native OpenHands smoke and historical experiment repository **for reference only**. The product branch's tree starts clean by design: do not merge the experimental tree back wholesale.

Goal: an autonomous, evidence-driven Java Maven OSS remediation workflow, executed by native OpenHands and gated by independent deterministic validation before GitHub draft-PR delivery. Preserve native API/SDK/Canvas and built-in hook semantics, not an invented service/API/UI/database.

Offline entry commands (no model or external mutation):

```bash
python3 -S -m native_remediation check-task --task examples/maven-task.json
python3 -S -m unittest discover -s tests_native -v
```

`prepare` performs authorized Git/Maven/OSV work but no model inference. `attach`
creates an idle native conversation. `run` and `resume` require the explicit
`--authorize-run-and-delivery` flag and native credential preflight. Do not use
the example as authorization to run a model or create a remediation PR.
