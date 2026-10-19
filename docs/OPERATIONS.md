# Native product operation

Implementation entry point: `python3 -m native_remediation` (or the optional
`oss-remediate` package entry point). No product server, API, UI, database,
background watcher or second reasoning agent is started by these commands.
Use the existing native Agent Server/SDK/tools **1.55.1**, Canvas **1.27.1**.
Model configuration is explicit in task JSON; no model is called by import,
`check-task`, `prepare`, `doctor`, `attach` or `status`.

## Inputs and preparation

`examples/maven-task.json` is a concrete editable example, **not authorization to
execute it**. Its base SHA comes from the earlier smoke; re-resolve and approve
the branch/SHA before a new task. `prepare` refuses remote branch drift before
and during clone. It creates a new private state directory and isolated detached
worktree; it will not overwrite an existing state directory.

The policy is the deterministic acceptance contract. Allow paths needed for the
actual goal, without forcing a Spring Boot strategy. Set allowed major movement,
protected effective properties, approved dependency removals, remaining finding
budget and optional target identifiers. Targets are optional: by default a real
baseline discovers findings and acceptance requires zero remaining/new findings.
The same vulnerability reported under a CVE/GHSA alias is still a remaining
finding. Maven tests may not decrease below baseline or `minimum_tests`.

Additional hard constraints require `{ "description": "...", "check": ["executable", "arg"] }`
entries. An unverified free-text constraint is rejected rather than silently
treated as satisfied. `tools.checks` holds additional approved acceptance command
argument lists. They run independently against baseline and candidate exports.
These trusted commands must actually test the described requirement; software
cannot infer that an arbitrary goal statement is proven by a scanner count.

Required: Python 3.12+, Git with existing repository HTTPS credentials, Maven,
Java appropriate to the project, OSV Scanner **2.6.0**, and an existing authorized
`gh` login. Executables can be explicit trusted paths. Optional SBRI/research
references identify installed scripts/docs usable through the native terminal;
they are not mandatory stages. No SBRI implementation or expensive automatic
analysis is embedded. Other scanners (including JFrog Xray) need their own
verified adapter; substituting their executable is rejected by version checks.

```bash
python3 -m native_remediation check-task --task examples/maven-task.json
# Future authorized deterministic preparation; downloads/build/OSV calls, no LLM:
python3 -m native_remediation prepare --task /private/approved-task.json \
  --state /private/persistent/new-task
```

Baseline and final acceptance use a fresh Git export, never the mutable agent
worktree. The validator runs `clean install` (includes verify/tests), resolved
JSON `maven-dependency-plugin:3.8.1:tree`, and aggregated effective POMs through
`maven-help-plugin:3.5.1:effective-pom`. All reactor graphs must match effective
models; scopes and paths remain in evidence. Local reactor coordinates are
identified separately. All external resolved package/version pairs are fed to
OSV as a generated CycloneDX inventory, using the supported 2.6.0 SBOM option,
`--all-packages`, `--all-vulns` and a trusted empty suppression config. All pairs
must appear in OSV output. Empty/incomplete coverage, scanner failures, timeouts,
missing modules and unexplained disappeared dependencies cannot become PASS.
Build/test failures are FAIL; uncertain resolution/scanner results are
INCONCLUSIVE. Baseline must be COMPLETE before idle attachment.

Coverage is explicitly the reactor's resolved **project dependency graphs** across
all scopes. Maven build-plugin dependencies, JDK and operating-system packages
are not covered; a task requiring those needs an additional independently verified
acceptance check/adapter. A clean project-dependency scan does not prove those
other surfaces vulnerability-free.

Primary Maven interface references:
[dependency tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html),
[effective POM](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html).
The checked installed OSV 2.6.0 `scan source --help` supports `--sbom` (deprecated
but supported), `--all-packages`, `--all-vulns`, and `--config`.

## Native attachment and explicit execution

Start/reuse the official native installation independently. Preserve its session
key/conversations. Do not start the historical product service. This repository
does not install, replace or restart the running native stack.

The native Agent Server must inherit `VERTEXAI_PROJECT`, `VERTEXAI_LOCATION` and
appropriate ADC discovery. Prefer user ADC created directly in a private persistent
directory, with `GOOGLE_APPLICATION_CREDENTIALS` explicitly referencing it at
native launch. Never commit credential contents or copy them into workspaces.
The previous temporary discovery symlink is not a durable setup. `doctor` uses
the running local Agent Server's actual Python executable and inherited environment
for two Google Auth refreshes and requires a valid token with >=300 seconds left.
No model call or project change occurs. Other model providers are explicit native
configuration, but their credential preflight is not yet implemented here.

Use the native session-key file path; never its value in command arguments:

```bash
python3 -m native_remediation doctor --state /private/persistent/new-task \
  --server http://127.0.0.1:18910 --key-file /private/native/session-key.txt
python3 -m native_remediation attach --state /private/persistent/new-task \
  --server http://127.0.0.1:18910 --key-file /private/native/session-key.txt
```

`attach` makes exactly one native create request, sends the stable task message
with `run: false`, then verifies effective model, tools, workspace and Stop hook.
This ordering matters: 1.55.1 stores explicit hooks in metadata but initializes
them lazily on the first message; immediately after creation GET can show null.
`AgentContext.system_message_suffix` supplies the operating model. Tools are
native terminal, file editor and task tracker; one Agent uses them autonomously.
No research claims are implied by a failed HTTP/tool request. For external
research, the agent can use available shell/network capabilities and supplied
references; there is no additional planner or research service.

Only after separate explicit paid execution and draft-delivery authorization:

```bash
python3 -m native_remediation run --state /private/persistent/new-task \
  --key-file /private/native/session-key.txt --authorize-run-and-delivery
```

This repeats credential/repository access preflight, writes a durable run intent,
POSTs `/run` once and exits. Native OpenHands owns the agent loop and events.
The agent uses the supplied `record --kind intent|outcome --document <JSON-file>`
command to retain concise cycle facts/uncertainty/assumptions, credible candidates,
strategy rationale and self-check outcomes, not hidden chain of thought. First
intent must precede material edits; outcome binds the candidate tree. The agent
can honestly report `bounded_failure`, which terminates without acceptance or PR.

Stop validation is synchronous. A rejected candidate returns actionable deny
feedback; the agent must reassess and record another bounded cycle. Repeated
Finish on the same rejected tree/cycle reuses feedback without rescanning.
Cycles, runs, iterations and command/validation time are bounded. Only independent
PASS can reach delivery. `allow` can also explicitly terminate BOUNDED_FAILURE;
**that is never product success**. Product success requires the exact-tree
validation and confirmed delivery artifacts, not native finish or hook allow.

## Delivery, observation and recovery

Delivery rechecks task/conversation/base/tree/evidence digests, current workspace,
remote base SHA and the authorized GitHub destination. It commits the accepted
tree directly, preserving the agent's HEAD/index. Branch creation uses an empty
lease and never pushes the base. A lock, fsynced local claim, intended commit SHA,
remote branch lookup and PR lookup prevent blind mutation replay. PR must be the
exact open draft with the validated head SHA and authorized base/repository.

```bash
python3 -m native_remediation status --state /private/persistent/new-task \
  --key-file /private/native/session-key.txt
```

Native events remain native; use its API or optional Canvas for observation.
Status fails closed if native finish has no trusted acceptance/delivery result.
An uncertain create/run response is **not** permission to resubmit. Inspect the
claimed conversation and native events first. After documented recovery evidence
and explicit authorization, `resume --reason "..." --authorize-run-and-delivery`
uses the same conversation, carries task digest/journal/current Git/feedback and
consumes the bounded run budget. It refuses running or successfully terminal
conversations. No automatic model retry is configured.

For an uncertain idle attachment, `attach --reconcile` reads the existing native
conversation/events, verifies the bound task message or sends it only if absent,
then verifies hooks. It never repeats conversation creation; unrelated, executed
or incomplete/ambiguous history blocks reconciliation.

`reconcile-delivery --state ...` is a short-lived explicit recovery command for
an already claimed independently accepted delivery. It can positively reconcile
a pushed branch or existing PR. If a PR POST may have happened but no exact PR
is found, it blocks rather than POSTing again. Never erase claims to retry.
An interrupted validation reservation consumes an attempt; it cannot become PASS
or automatically rescan. Explicit bounded `resume` records it as INCONCLUSIVE
before any later attempt.

## Durable artifacts and boundaries

The private state directory contains `task.json` (stable task/digest/conversation),
`workspace`, `source.git`, baseline/effective models/resolved graphs, private Maven
cache, `journal`, per-attempt intent/evaluation/validation, feedback, run intents,
delivery claim and result. JSON writes are atomic and fsynced. Keep these files
outside Git and outside the agent worktree, in persistent storage with restrictive
permissions. Do not publish raw tool logs, source exports or native authentication
metadata. Native history is not copied into a second event database.

This is local single-host durability, not a distributed transaction system. Same-OS-user
shell/Maven execution is not a security sandbox: an adversarial agent or build can
access host credentials/state. Symlink/submodule trees are explicitly unsupported;
builds requiring a `.git` directory in the validation export are not supported.
Changed non-numeric Maven versions return INCONCLUSIVE rather than guessing
qualifier ordering. Tests alone do not prove behavioral compatibility. Overall
task time is checked at dispatch/validation boundaries; native iterations/model
timeouts and command process-group timeouts bound work, but no external watchdog
enforces a hard wall-clock cutoff during arbitrary native terminal work. A native
hook infrastructure failure may fail open; `status` still refuses acceptance
without independent PASS and delivery evidence. Production multi-user isolation,
durable ADC setup and Canvas browser rendering remain open verification items.
