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

**Host authority isolation is explicitly deferred, not an execution blocker.**
The legacy `require_independent_authority()` checkpoint is nonblocking under the
approved contract. Deterministic acceptance is separate from agent self-reporting,
but is NOT protected from the same host user. Baseline/integrity/policy checks,
explicit model authorization and PASS-only delivery remain enforced. No new mode,
bypass flag or replacement infrastructure. Use only an approved repository/task.

See [first-run configuration and exact commands](docs/OPERATIONS.md#first-real-run).
For repeated authorized runs with automatic sanitized evidence publication, use
`bash scripts/openhands/sdk-cloudshell-setup.sh live --task examples/maven-task.json --authorize-model-execution --publish-evidence`.
See [batch operation and existing-state reporting](docs/OPERATIONS.md#one-command-live-execution-and-evidence-publication).
The SDK Gemini path is reachable; a complete real remediation is not yet proven.
Configure the approved Vertex project/location and ADC before running. Static
retirement tables do not block the configured model or prove actual availability.
Scanner configuration and adapter extension: [configuration](docs/CONFIGURATION.md#scanner-adapter-contract).

Read [operations](docs/OPERATIONS.md), [implementation/proof](docs/IMPLEMENTATION.md),
[contract](PRODUCT-CONTRACT.md), [historical parity](docs/POC-PARITY.md),
[configuration](docs/CONFIGURATION.md) and [handoff](ENGINEERING-HANDOFF.md).
Offline checks:
```bash
python3 -S -m native_remediation check-task --task examples/maven-task.json
python3 -S -m unittest discover -s tests_native -v
# Existing installed SDK Python:
python -m unittest discover -s tests_native -v
```

No Gemini execution, target modification, real Maven/OSV analysis or PR is authorized.
Historical smoke/PR #214 at f72e5308704960ee911f382f96bf0b7948435216 remains separate
evidence, not proof of this product's security or full remediation behavior.
