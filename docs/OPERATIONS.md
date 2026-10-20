# Autonomous OSS Vulnerability Remediation — standalone SDK operations

## Runtime and prerequisites

Use the existing Python 3.12+ environment with `openhands-sdk[vertex]==1.55.1`
and `openhands-tools==1.55.1`. No Agent Server, session key, Canvas, product service,
database or watcher is required. Commands run in the foreground; OpenHands owns
the single agent loop. Never run these paid/delivery commands without authorization.

An approved task pins repository, base branch/SHA, goal, deterministic constraints,
policy, limits and draft destination. `examples/maven-task.json` is illustrative,
not current approval of its old smoke base. Extra constraints require real check
argv; scanner counts do not prove arbitrary free-text goals. Allowed change paths,
major-version/downgrade policy, dependency removals, protected properties and
test/finding budgets remain explicit. No mandatory Spring Boot upgrade or SBRI step.

Set `sandbox.image` to an **existing local Docker image ID**
(`sha256:` plus 64 lowercase hex digits). Tags and automatic pulls are refused.
The image must provide trusted bash, Git, Java/Maven, OSV Scanner 2.6.0, and the
task's optional tools/references and offline dependency/vulnerability data.
Executables/check paths in the task refer to the image, not host executables.
The image must support the host numeric UID/GID and HOME=/tmp. Provisioning is an
operator prerequisite, not an automatic package-install/model step.

There is currently **no image installed**, and no real container/toolchain run
has been proved here. Containers have `--network=none`: no metadata-server access,
Internet, arbitrary dependency downloads or online research. The approved image/
offline repositories must satisfy dependency/plugin/OSV data needs, or preparation
fails closed. Networked deployment needs reviewed credential-safe egress; no
network override is offered. SBRI/research references are optional image-local
evidence, not claims that web research is available.

Docker daemon/host kernel, operator-owned image, SDK installation, private state
and operator home/plugins are trusted. Do not mount Docker sockets, host home,
ADC files or credentials into the image. Do not run two different trusted control
processes against one task outside the provided execution lock.

## Lifecycle and commands

```bash
python -m native_remediation check-task --task /private/approved-task.json
# Normal execution: initializes SDK, prepares/gates, sends objective, runs.
python -m native_remediation start --task /private/approved-task.json \
  --state /private/persistent/new-task --authorize-run-and-delivery
# Diagnostic preparation only: no task message, inference or delivery.
python -m native_remediation prepare --task /private/approved-task.json \
  --state /private/persistent/new-task
# Run an already prepared idle task after separate authorization:
python -m native_remediation run --state /private/persistent/new-task \
  --authorize-run-and-delivery
```

`start` does not hide remote orchestration: it uses only local SDK objects and
trusted deterministic Python preparation, followed by SDK send_message/run.
`execute_tool()` is supported locally but unnecessary for this trusted validator;
it bypasses agent security checks and is not used as a preparation proof.

A native conversation is created before preparation without inference. Git clones
only the approved base and creates the isolated worktree. Repository build code
executes only in restricted containers. Baseline must be COMPLETE before a durable
`preparation.json` is issued, bound to task digest, native conversation, repository,
approved commit/tree and baseline digest. Every run/recovery checks that receipt,
task deadline, first-run workspace, remote base, sandbox and credentials. Missing,
tampered, stale or incomplete evidence blocks execution, regardless of messages.
Interrupted preparation is not automatically repeated; preserve evidence and
diagnose. Existing state directories are never overwritten.

SDK history/state live in `state/conversations/<UUID-hex>/`. The SDK automatically
restores the same ID; missing persistence after preparation intent blocks rather
than creating a replacement. Preparation never sends the task or calls run().
Sending the task lazily initializes native tools/hooks; effective hooks/tools are
checked before run(). No model call occurs in initialization or preparation.

LocalWorkspace points to the trusted empty `state/control`, not repository
contents. Inside the native terminal, that same pathname is the repository mount.
This keeps repository plugins/skills/configuration away from host SDK discovery.
The native terminal performs inspection/editing/testing via normal shell commands;
the host file-editor tool is intentionally not exposed. Native task_tracker is
available; `cycle_evidence(record_type, document)` records concise structured
intent/outcome, not private reasoning or acceptance. Record intent before edits.
The tool takes data only, never a path or command. Baseline is read-only at
`/baseline.json` and `/baseline/` in the terminal.

## Independent Stop and delivery

Native Stop calls the existing short-lived CLI hook. It verifies conversation/
control-workspace identity and preparation, stops the agent container (including
background descendants), captures the actual candidate Git tree and runs independent
Maven/OSV acceptance. On denial, use native terminal `reset=true` to start a new
isolated shell for reassessment; no new agent or conversation is created.

Acceptance exports exact Git blobs (not export-ignore-sensitive archives), builds
with Maven clean install/tests, resolves project dependency graphs across the
reactor, checks effective POMs/test coverage and task constraints, and executes OSV
2.6.0 with exact package coverage and no trusted suppressions. Build-plugin/JDK/OS
vulnerabilities are outside the project-dependency scanner scope; tasks needing
them require separately verified checks. Errors or unknown coverage cannot PASS.
Raw source/build outputs are not trusted acceptance decisions. Command stdout/
stderr and parsed acceptance are written by host code outside writable mounts.

FAIL/INCONCLUSIVE returns feedback for bounded reassessment; identical tree/cycle
does not rescan. Explicit BOUNDED_FAILURE may allow native termination but never
acceptance/delivery. Only independent PASS permits delivery of the exact tested
tree to the authorized base/destination. Create-only branch behavior, commit parent/
tree checks, draft/head/base verification, durable claims and positive reconciliation
are preserved. Ambiguous push/POST never authorizes duplicate mutation.

Native hook infrastructure can fail open if the command cannot start. Therefore
native finish/allow is never product success: status requires trusted exact-tree
PASS and confirmed draft evidence. The outer SDK caller also stops remaining agent
containers after run/close; inability to establish quiescence blocks acceptance.

## Recovery, credentials and observation

```bash
python -m native_remediation status --state /private/persistent/task
python -m native_remediation doctor --state /private/persistent/task
python -m native_remediation resume --state /private/persistent/task \
  --reason "documented interrupted execution" --authorize-run-and-delivery
python -m native_remediation reconcile-delivery --state /private/persistent/task
```

Resume restores native SDK history and rechecks preparation; never regenerates
baseline or creates another conversation. Run/time/cycle budgets and per-task
lifetime execution lock prevent concurrent/unbounded execution. Run intents are
retained because native persistence alone cannot reconcile external delivery.
A task message without a run intent is an ambiguous interruption: inspect, do not
replay. Uncertain delivery is reconciled from existing independent PASS/claim only.

Vertex ADC is refreshed by the exact current SDK Python/environment, requiring
>=300 seconds validity; no Agent Server process discovery remains. Use persistent
private user ADC and explicit GOOGLE_APPLICATION_CREDENTIALS plus VERTEXAI_PROJECT/
VERTEXAI_LOCATION. No service-account key or credentials in task inputs/prompt/
containers. GitHub uses the existing authorized gh credentials on the host only.
Doctor/preflight performs credential refresh/read-only GitHub checks, no inference.

Status reads native local state/stats without running; no mirrored event database.
Standalone SDK conversations are not automatically registered in Agent Server or
Canvas. Browser rendering remains unverified; local native persistence is the
observation source. Old remote task state/evidence is retained, not auto-migrated.

## Offline verification

```bash
python3 -S -m unittest tests_native.test_product tests_native.test_sandbox -v
# Installed SDK Python (includes real no-inference construction/resume/Stop):
python -m unittest tests_native.test_product tests_native.test_sdk_contract tests_native.test_sandbox -v
python3 -S -m native_remediation check-task --task examples/maven-task.json
python3 -S -m compileall -q native_remediation tests_native
git diff --check
```

Historical remote contract probes are preserved separately; they need not be
repeated for standalone SDK verification. No offline result is live remediation,
container security certification, real OSV coverage or GitHub delivery proof.
