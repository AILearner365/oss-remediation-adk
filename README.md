# Autonomous OSS Vulnerability Remediation

One autonomous engineering agent using the **standalone OpenHands SDK/tools 1.55.1**.
Branch: `autonomous-oss-remediation`. No custom server, database, scheduler,
UI, model loop, Docker image, shell launcher or offline-only network requirement.

The local path uses `LocalWorkspace(state/workspace)` and native persistent
`TerminalTool` with the host shell. Existing deterministic Maven/OSV code uses
the existing bounded local argv executor and host tools/proxies. Native
Conversation persistence/resume, the durable COMPLETE preparation gate, concise
decision/outcome evidence, Stop validation and exact-tree PASS-only delivery remain.
The default is **report_only**, not permission to push. Draft PRs require explicit
task authorization and independent PASS.

Historical POC engineering behavior is retained through native general context
and SDK-loaded decision/Maven Skills. Native `validate_remediation` reuses the
validator for agent self-checks without spending Stop attempts or accepting work.
Optional `sbri_intelligence` calls the existing SBRI CLI, if installed; no engine
or mandatory Spring Boot strategy is added. Automatic phase evidence indexes
native trajectories/stats, Git changes and validation reports without asking the
agent to fill a questionnaire at every step.

**LocalWorkspace is not a sandbox.** Private state/policy/preparation/acceptance
records and SDK persistence are outside the repository workspace. No agent tool
provides acceptance/delivery authority. However a same-user shell or repository
build can still access those files and host credentials. Directory placement,
0600 permissions, stripped environment variables and instructions do not enforce
separation from that same OS user.

**Live product execution remains BLOCKED on that exact mandatory trust guarantee.**
`require_independent_authority()` refuses real repository build/acceptance, model
dispatch and GitHub delivery; there is no bypass flag or replacement infrastructure.
Safe trusted temporary fixtures test the local mechanisms without claiming this
boundary exists. This is not a Docker/image or remote Agent Server limitation.

Read [operations](docs/OPERATIONS.md), [implementation/proof](docs/IMPLEMENTATION.md),
[contract](PRODUCT-CONTRACT.md), [historical parity](docs/POC-PARITY.md),
[configuration](docs/CONFIGURATION.md) and [handoff](ENGINEERING-HANDOFF.md).
Offline checks:
```bash
python3 -S -m native_remediation check-task --task examples/maven-task.json
python3 -S -m unittest tests_native.test_product tests_native.test_local_execution tests_native.test_parity -v
# Existing installed SDK Python:
python -m unittest tests_native.test_product tests_native.test_sdk_contract tests_native.test_local_execution tests_native.test_parity tests_native.test_sdk_parity -v
```

No Gemini execution, target modification, real Maven/OSV analysis or PR is authorized.
Historical smoke/PR #214 at f72e5308704960ee911f382f96bf0b7948435216 remains separate
evidence, not proof of this product's security or full remediation behavior.
