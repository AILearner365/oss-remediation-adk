# Autonomous OSS Vulnerability Remediation

A single autonomous engineering agent built on the **standalone OpenHands Python
SDK 1.55.1**. No Agent Server, custom server, database, scheduler, UI or model loop.
Branch: `autonomous-oss-remediation`; `openhands-native-product` remains preserved.

**Implemented and offline-verified, not live-proven remediation.** The SDK
conversation is created idle, deterministic preparation completes, and a durable
identity-bound baseline receipt is checked before sending the objective and
calling `conversation.run()`. Recovery restores native persistence and checks
the receipt again. Independent native Stop validation alone can authorize delivery.

Agent commands use the native TerminalTool with a container shell; repository
builds are also containerized. The host holds preparation/acceptance evidence and
delivery credentials. There is no unsafe host-execution fallback. An approved,
locally provisioned immutable toolchain image is required and is **not present in
the current environment**. Network is disabled inside these containers; arbitrary
online Maven resolution/research is not yet supported. See the actual limits in
[operations](docs/OPERATIONS.md), [implementation/proof](docs/IMPLEMENTATION.md)
and the [contract](PRODUCT-CONTRACT.md).

Offline checks (no model, target modifications or PR):
```bash
python3 -S -m native_remediation check-task --task examples/maven-task.json
python3 -S -m unittest tests_native.test_product tests_native.test_sandbox -v
# In the existing SDK 1.55.1 Python environment:
python -m unittest tests_native.test_sdk_contract -v
```

The previous remote-server blocker is retained as [historical evidence](docs/NATIVE-PREPARATION-BLOCKER.md),
not a blocker to the standalone SDK calling pattern. Milestone 1 evidence and
PR #214 remain at commit `f72e5308704960ee911f382f96bf0b7948435216`; they prove
the prior one-file smoke, not this Maven/OSV product path. No live run is authorized
by this README or by passing offline tests.
