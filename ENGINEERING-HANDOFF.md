# Autonomous OSS Vulnerability Remediation — engineering handoff

Product branch: `autonomous-oss-remediation`. Preserve the original local/remote
`openhands-native-product` branch at `11431b428a69f4525679bda5880bf0a0d05137bc`.
Read [PRODUCT-CONTRACT.md](PRODUCT-CONTRACT.md) and [operations](docs/OPERATIONS.md).

## Implemented direction

Use the official standalone OpenHands SDK/tools 1.55.1. `native.open_conversation`
uses Conversation, LocalWorkspace, persistence_dir, conversation_id and explicit
native Stop hooks. The supported caller sequence is idle SDK initialization,
trusted deterministic preparation/baseline, durable COMPLETE gate, send_message,
run. This replaces remote HTTP creation, lazy-hook attachment reconciliation and
remote dispatch. No SDK internals were changed and no second agent loop was added.

Keep existing repository/policy checks, exact Git exports, Maven/OSV coverage and
PASS/FAIL/INCONCLUSIVE acceptance, bounded intent/outcome records, and draft-only
exact-tree delivery with claims/reconciliation. Native SDK persistence owns history
and execution state. The application owns only task/evidence/budgets/side-effect claims.

LocalWorkspace itself is not an isolation boundary. Host control workspace is
private, not the agent repository. Native terminal shell_path enters a restricted,
short-lived Docker container. Only repository files are writable to the agent;
Git metadata and baseline are read-only. Repository builds see only raw source,
build cache and explicitly supplied scanner inputs, never trusted decisions or
credentials. A small SDK cycle_evidence tool records untrusted agent-authored
intent/outcome without granting acceptance or arbitrary host execution.

## Verified versus remaining

Focused offline tests cover idle native SDK creation/restoration without inference,
preparation ordering/failure, durable evidence and one-shot/bounded recovery gates,
native Stop denial, independent validation and exact-tree delivery. Container
launch policy is tested with doubles, not a live isolation or remediation proof.
Historical remote probes remain available but are not repeated by these checks.

The environment has no approved local toolchain image. Provision an immutable
image ID and offline dependencies/SBRI/research references, then verify the real
container boundary/toolchain without inference. Network is deliberately disabled;
online Maven/OSV/research requires separately reviewed egress controls that cannot
expose host/cloud credentials. Do not enable bridge/host networking as a shortcut.
Persistent ADC, local-claim durability and Canvas browser rendering remain
deployment/unverified limitations. SDK conversations are not automatically visible
in the old Agent Server/Canvas.

No model call, live remediation, target edit or PR is authorized. Do not claim
full live readiness from mocks or repeat the remote-server architecture investigation.
