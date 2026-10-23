# Autonomous OSS Vulnerability Remediation — local SDK operations

## One-command live execution and evidence publication

After approving the task's Gemini model and verifying existing Cloud Shell ADC,
run from the product repository. The setup entry point automatically supplies
the approved project `deutschebank-aipocs` and location `us-central1` when missing.
Explicit `VERTEXAI_PROJECT` (then `GOOGLE_CLOUD_PROJECT`) and `VERTEXAI_LOCATION`
override the corresponding defaults; credentials are never configured or stored:

```bash
bash scripts/openhands/sdk-cloudshell-setup.sh live --task examples/maven-task.json --authorize-model-execution --publish-evidence
```

The wrapper retains the explicitly configured model. A published lifecycle date
does not prove that this project/region rejects inference; no static retirement
list blocks the approved model, and no model is silently substituted.
Actual inference availability remains unproven until a provider response.
Prerequisites: Python 3, uv if
SDK installation is needed, Git commit identity/credentials, Maven/Java/OSV and
approved Vertex access. Host authority isolation remains explicitly deferred.

Existing prepare/verify/test/python commands remain. Live reuses prepare (pinned
SDK/Tools 1.55.1, installed tools and uv caches), NOT the offline test suite.
Contract validation, SDK/tool/known-model checks, existing ADC/delivery checks
and approved remote-base verification precede exactly ONE existing product CLI
start. Product/SDK own preparation, baseline, model loop, Stop and delivery. No
new agent loop, fixture mode or lifecycle engine. ADC/model-name checks do not
prove inference availability, regional access, IAM or quota. Invalid Vertex
configuration still fails closed; these operator-approved
defaults are exported consistently to preflight and the SDK, not inferred from
an unrelated active gcloud configuration.
Both flags are required for an accepted live invocation. Authorization errors
are captured without executing the product; no publication flag means no push.

### Generated evidence layout

Default private root: ~/.local/state/oss-remediation/live, not ephemeral /tmp.
Override with --runs-dir /approved/private/path. Each invocation gets a new 0700
directory; live never reuses or automatically retries a state:

```text
<private-root>/<timestamp>-<uuid>/
  task-input.json             private approved task
  invocation.json             batch phase outcomes
  setup.stdout/.stderr        private SDK preparation logs
  preflight.stdout/.stderr    private prerequisite logs
  checks.json                 prerequisite results
  execution.stdout/.stderr    private product console output
  state/                      COMPLETE product state (when initialized)
    conversations/ workspace/ baseline/ attempts/ self-validation/ sbri/ evidence/
  report.json                 sanitized public projection, retained locally too
  publication.json            verified SHA or explicit PUBLICATION_FAILED
  failure.json / *-error.json  actual private diagnostics, if applicable

<product>/docs/evidence/live-runs/<timestamp>-<uuid>/report.json
```

Public data is an allowlisted projection, NOT raw logs with regex redaction:
statuses, numeric usage/tests, command exit/timing, inventory/coverage counts,
finding IDs, Maven coordinates/versions/paths, available CVSS/fix evidence, exact
acceptance/delivery outcome and PR URL, decision/cycle indexes, and private-artifact
SHA references. Task/agent prose, command argv,
credentials/config files, unrestricted scanner prose, logs and workspace snapshots
never enter Git. Known static validator diagnostics are published; other text is
PRIVATE_DIAGNOSTIC with a fingerprint/private reference. Narrative engineering
choices remain available privately, not automatically published. Approved
repository/base/model identity is public metadata; never put secrets there.

NOT_EXECUTED/NOT_CHECKED differs from failed/inconclusive/interrupted. Unknown
OSV findings are null/NOT_ASSESSED, not zero. Dispatch claims differ from observed
response events; native finish is not independent acceptance. Malformed/unsafe/
inconsistent evidence marks reportComplete false; export exceptions produce an
explicit REPORT_INCOMPLETE report. Complete private state is retained; public
reports are deliberately bounded summaries, not full conversation exports.

### Publication and recovery

With --publish-evidence, finalization attempts publication after success, failure
or caught interruption. Product branch and authorized origin are verified;
local/remote HEAD must agree before execution, and a changed HEAD during execution
blocks publication. An isolated index and atomic expected-parent ref update commit
only this run's report. Unrelated staged/unstaged files remain untouched. No Git
content filter/hook can inject bytes into the report blob. No target-repository
operation is part of publication. No force push, merge, history rewrite or blind
retry. A push failure can leave a new LOCAL evidence commit; inspect/reconcile
manually, do not rerun the remediation to republish it.

Console output and private publication.json contain the positively verified
publishing SHA or publishing failure. The immutable public report says publication
was requested, not that its own future commit was already pushed. Nonzero exit
means remediation failed, report is incomplete or publication failed; successful
evidence publication does not turn failed remediation into success.

SIGINT/SIGTERM get best-effort process-group interruption and finalization.
SIGKILL, host loss, disk failure or another interruption during finalization cannot
guarantee capture/publication. Existing model/task limits are unchanged; no new
background-process containment or hard run deadline is claimed.

### Existing-state export without rerun

```bash
bash scripts/openhands/sdk-cloudshell-setup.sh report --state /tmp/oss-remediation-runs/first-report-only --publish-evidence
```

No SDK install, preflight refresh, checkout/build, inference, validation or task
rerun occurs. Omit --publish-evidence for local-only export. Source state is
read-only; each export has a unique ID. Missing historical checks are NOT_CHECKED.
Inspection of that state found `Unexpected OSV package identity`: build/resolve
passed, scan exited 1, coverage normalization failed; 88 reported identities did
not match 88 expected inventory identities. Findings are NOT_ASSESSED. No run
claim or model response existed. This exporter does not fix/relax validation.

## Actual execution model

Use the existing Python 3.12+ environment with SDK/tools 1.55.1 and installed
Cloud Shell Git, Java/Maven, OSV Scanner 2.6.0 and gh. LocalWorkspace's working
directory is `state/workspace`, the actual isolated Git worktree. TerminalTool
uses the native subprocess-backed persistent host shell, without shell_path or
Docker. No image, image preflight, forced offline mode or network override exists.

Existing Maven/OSV validation uses the bounded local argv helper in files.py
(no shell injection or automatic retries). PATH, HOME, Java/TLS settings and
uppercase/lowercase HTTP(S)/ALL/NO_PROXY settings are retained. Explicit model/GitHub
credential variables are omitted from build children, but host file/metadata
access is NOT prevented. Host Maven settings/proxies can supply authorized normal
dependency downloads; OSV/network research are not artificially disabled.
Offline unit tests do not exercise those network paths. A separate controlled
retained-SBRI backend diagnostic exercised real Maven/OSV networking; see the
[verification evidence](SDK-P0-P1-READINESS-REVIEW.md#current-verification-assessment--2026-10-20).

Optional SBRI/research references point to host scripts/docs, not container paths.
An optional pre-edit SBRI applicability check supplies bounded evidence before
the task message; unavailable/non-applicable intelligence is not a security
conclusion and does not replace baseline COMPLETE. sbri_intelligence permits
additional version/range/scope investigations using the existing CLI. The CLI is
currently not installed here. The historical backend was verified directly from
a temporary Git extraction on an authored fixture, not through the P0-blocked
product adapter; production SBRI remains unavailable until a compatible CLI is configured. No fixed Boot
strategy, second engine or mandatory successful SBRI stage is introduced.

## Trust limitation and fail-closed behavior

Trusted task/policy, preparation receipts, baseline/acceptance records, SDK
persistence, journals, claims and credentials live outside the agent repository.
Private files/locks protect against accidental edits/other users, not the same
host user. No agent tool grants direct acceptance/delivery operations; the
cycle_evidence tool records agent-authored data only. An unrestricted shell still
can access sibling files, HOME, credentials and processes. LocalWorkspace is not
a sandbox, cwd is not containment, and production security isolation is not claimed.

The guarantee that agent commands/builds cannot alter trusted records or access
delivery credentials is **not supported here and explicitly deferred** by product
decision on 2026-10-22. files.require_independent_authority() is a documented
nonblocking compatibility checkpoint; no new mode or per-task bypass exists.
Normal prepare/start/run/acceptance/delivery may execute with this known host
limitation. Separately invoked deterministic acceptance remains mandatory, but
must not be described as process/filesystem-isolated from agent/build commands.
Baseline, evidence integrity, task policy, authorization and delivery checks
still fail closed. No new isolation infrastructure is introduced.

## Preserved lifecycle and interfaces

The implemented flow is:
1. Initialize/restore Conversation without inference.
2. Deterministically prepare the approved repository/base and collect baseline.
3. Issue preparation.json only on COMPLETE, bound to native conversation, task
   digest, repository, approved SHA/tree, baseline digest and completion time.
4. Recheck evidence/deadline/base/first-run workspace, then send_message/run.
5. One native agent investigates, selects strategies, edits, self-tests/reassesses.
6. Native Stop validates independently; deny with feedback or record exact-tree PASS.
7. report_only returns VALIDATED without remote mutation. Explicitly authorized
   draft_pr verifies delivery before allowing accepted completion.

These entry points preserve that flow and its deterministic/authorization gates:
```bash
python -m native_remediation check-task --task /private/approved-task.json
python -m native_remediation prepare --task /private/approved-task.json --state /private/new-task
python -m native_remediation start --task /private/approved-task.json --state /private/new-task --authorize-model-execution
python -m native_remediation run --state /private/task --authorize-model-execution
python -m native_remediation resume --state /private/task --reason "documented interruption" --authorize-model-execution
python -m native_remediation status --state /private/task
python -m native_remediation doctor --state /private/task
python -m native_remediation reconcile-delivery --state /private/task
python -m native_remediation self-validate --state /private/task
python -m native_remediation sbri --state /private/task --ranges 4.1.x --scopes compile runtime
python -m native_remediation sbri --state /private/task --refresh
```

check-task is offline validation, not readiness or permission. The example base is
historical, not fresh approval. Doctor performs current-runtime ADC refresh and
read-only GitHub checks; it does not prove trust separation. No server/session-key
argument, attach stage, watcher or custom lifecycle engine exists.

Native state/events/stats persist under state/conversations/<UUID-hex>. The same
ID/directory restores the saved agent using agent=None; task-pinned settings are
checked, excluding only SDK-generated prompt time. Missing persistence or missing/
incomplete/stale/tampered preparation blocks rather than recreating or rebaselining.
Run claims, a lifetime execution lock, explicit bounded resume and existing delivery
reconciliation remain. Old Docker-mode state is preserved, not silently migrated.

Native terminal performs ordinary inspection/editing/Maven/OSV/research commands.
task_tracker is native. General engineering context is stable; two native Skills
are selected through AgentContext and keyword-loaded by the initial task. No
ambient user/public/project Skill discovery is enabled. guidance.json records
source/render hashes and triggered names, not a claim of model use or compliance.
cycle_evidence records concise material decisions and outcomes when useful, not
every command/edit. Missing explicit outcome is recorded honestly at Stop and
still requires independent validation. Legacy intent records remain readable.
validate_remediation calls the same full-project validator into self-validation/;
it never writes authoritative attempts/feedback/results/delivery or spends Stop
attempts. sbri_intelligence is optional evidence, not acceptance or compatibility.
The model loop, task history and tool execution are native SDK facilities.
execute_tool is tested for safe no-inference probes, not required for trusted
deterministic Python preparation. Host project plugin discovery is another reason
not to treat repository-controlled content as safe before lazy initialization.

## Acceptance/delivery safeguards retained

Exact Git blobs are exported independently of export-ignore/subst attributes.
Maven clean install/tests, resolved reactor project-dependency coverage, effective
POMs, test counts, task-specific constraints and OSV 2.6.0 exact package coverage
remain mandatory. Build-plugin/JDK/OS findings require separate verified checks.
FAIL and INCONCLUSIVE never become PASS; self-checks and native finish do not accept.

Repeated rejected tree/cycle reuses feedback. Budget exhaustion/bounded failure
may terminate natively without acceptance or PR. Only explicitly authorized exact-tree independent PASS
can enter the retained draft delivery contract: authorized repository/base SHA,
commit parent/tree, create-only branch, exact open draft head/base checks, durable
claim and positive reconciliation; uncertain push/POST is never blindly repeated.
Host isolation is future work, not a delivery gate. Explicit authorization,
independent deterministic PASS and exact-tree/remote identity checks are still gates.

## First real run

Current code reaches the SDK's configured real Gemini completion path. No
scripted response source is imported by production code. The no-model provider
boundary regression executes real factory/run/Agent.step/LLM.generate, then
traps completion BEFORE a provider request; it is reachability proof, not a
successful real request. Full Gemini remediation/feedback/delivery needs a
separately authorized first run.

Payloads (both schema-validated; review and approve before use):

- [report_only](../examples/maven-task.json): no branch push or PR.
- [draft_pr](../examples/maven-task-draft-pr.json): explicit task authorization;
  one task-owned create-only branch and open draft only after PASS, never base push.

Both refer to approved test base `main-runrunning` at
`9ea1b0ed5ca255db0fc7c659d050896d3ed5db78`, observed unchanged on 2026-10-22.
Check it again before starting; a moved base must be explicitly re-approved,
not silently substituted. These example files do not authorize a run by themselves.
Their configured `vertex_ai/gemini-2.5-flash` is retained. Lifecycle documentation
is advisory, not a project-specific availability probe. Preflight validates ADC
and configuration, not inference. The actual provider response determines whether
the approved model can run; never substitute a model following a failed request.

From the product repository, use the installed runtime and an explicitly approved
Vertex project/location. The setup script now uses the operator-approved defaults
documented in AGENTS.md; direct Python CLI use still requires exported values.
No service-account key is required or recommended. Retain the current
authorized ADC source if it refreshes reliably; if an existing refreshed user ADC
file is required, point GOOGLE_APPLICATION_CREDENTIALS at that file outside the
workspace without copying its contents. Temporary Cloud Shell metadata/ADC and
/tmp SDK installation may disappear/expire. Do not lower the 300-second check.

```bash
export VERTEXAI_PROJECT='YOUR_APPROVED_VERTEX_PROJECT'
export VERTEXAI_LOCATION='YOUR_APPROVED_VERTEX_LOCATION'
export REMEDIATION_MODEL='vertex_ai/YOUR_APPROVED_SUPPORTED_GEMINI_MODEL'
SDK_PY=/tmp/openhands-sdk-1.55.1/venv/bin/python
mkdir -p -m 700 /tmp/oss-remediation-runs
# jq creates explicit task payloads, not another product execution mode.
# Review these files and approve the model/constraints before using them.
jq --arg model "$REMEDIATION_MODEL" '.model = $model' examples/maven-task.json > /tmp/oss-remediation-runs/approved-report-only.json
jq --arg model "$REMEDIATION_MODEL" '.model = $model' examples/maven-task-draft-pr.json > /tmp/oss-remediation-runs/approved-draft-pr.json
# No model/target mutation: schema, ADC refresh, optional draft push-permission GET.
TASK_JSON=/tmp/oss-remediation-runs/approved-report-only.json
"$SDK_PY" -m native_remediation check-task --task "$TASK_JSON"
"$SDK_PY" -c 'import json,sys; from native_remediation.contract import load_task; from native_remediation.files import read; from native_remediation.preflight import check; print(json.dumps(check(load_task(read(sys.argv[1])))))' "$TASK_JSON"
git ls-remote https://github.com/AILearner365/maven-multimodule-app.git refs/heads/main-runrunning
```

Ensure the Vertex AI API, selected region/model access, quota/billing and IAM
permission are available in that approved project. ADC refresh does not prove
prediction permission. Current inspection found SDK/tools 1.55.1, Java 21,
Maven 3.9.16 and OSV 2.6.0; GitHub repository read/push permission GET succeeded.
ADC metadata credentials refreshed above 300 seconds, but project/location were
unset, so normal Vertex preflight failed configuration. No credentials, global
Cloud Shell configuration or model settings were changed to conceal that failure.

Maven settings/proxies/repositories and OSV networking must resolve the actual
project; baseline COMPLETE is the decisive check. Optional SBRI is not installed
on PATH here: default auto reports UNAVAILABLE without blocking preparation.
If desired, configure sbri.executable to an existing compatible CLI, not to a
test fixture. SBRI is not required to start or to establish independent PASS.

Only after reviewing the task, setting valid Vertex configuration and obtaining
run authorization, execute **one** of these existing CLI paths (not both):

```bash
# Report-only first run. Parent is private and OUTSIDE the target workspace;
# start creates the fresh task directory itself (it must not already exist).
mkdir -p -m 700 /tmp/oss-remediation-runs
"$SDK_PY" -m native_remediation start --task /tmp/oss-remediation-runs/approved-report-only.json --state /tmp/oss-remediation-runs/first-report-only --authorize-model-execution
"$SDK_PY" -m native_remediation status --state /tmp/oss-remediation-runs/first-report-only

# Alternative only if draft-PR delivery is explicitly authorized:
"$SDK_PY" -m native_remediation start --task /tmp/oss-remediation-runs/approved-draft-pr.json --state /tmp/oss-remediation-runs/first-draft-pr --authorize-model-execution
"$SDK_PY" -m native_remediation status --state /tmp/oss-remediation-runs/first-draft-pr
```

start initializes the SDK, prepares/validates the baseline, then preflights and
dispatches. Do not run these commands in this implementation task. Preserve all
task directories; /tmp is ephemeral, so select durable private storage before
relying on restart survival. Never blindly rerun start or create another task
after an uncertain response. Inspect status/evidence. Explicit bounded recovery:

```bash
"$SDK_PY" -m native_remediation resume --state /tmp/oss-remediation-runs/first-report-only --reason 'Documented interruption; prior state inspected' --authorize-model-execution
# For an already accepted/claimed uncertain draft delivery, reconcile instead:
"$SDK_PY" -m native_remediation reconcile-delivery --state /tmp/oss-remediation-runs/first-draft-pr
```

Recovery still requires intact preparation/persistence and remaining budgets;
interrupted preparation is not automatically repeated. A native finish alone is
not product success. Distinguish VALIDATED, DELIVERED, BOUNDED_FAILURE and BLOCKED.

## P1 baseline and execution semantics

Baseline COMPLETE requires matching reactor graphs/resolved inventory, exact OSV
coverage, configured minimum tests and successful required checks. All existing
tools.checks and constraints are baseline AND candidate invariants; there is no
automatic final-only exemption. Vulnerability findings may exist in a reliable
baseline, but missing coverage, failed required checks and invalid evidence cannot
start the agent. Receipt creation and every dispatch/resume recheck this contract.

Native PreToolUse requires explicit finite positive terminal timeouts within
command_seconds and remaining task admission time. Use native polling/interrupts;
Ctrl-C/Ctrl-D/Ctrl-Z control inputs remain available after expiry. A native timeout
returns control, not a guarantee to kill the command/background descendants.
task_seconds gates dispatch, terminal admission and deterministic evaluations; it
is NOT an enforced hard wall-clock kill switch for conversation.run(). Deterministic
Maven/OSV/SBRI still use bounded commands and existing process-group cleanup. Hook
infrastructure can fail open in SDK 1.55.1; direct execute_tool bypasses action
hooks. Production remains P0-blocked, not protected by this policy alone.

Both pre-edit and agent SBRI calls automatically forward approved Maven profiles,
scopes and timeouts. Fresh successful results are reused, expired results refreshed,
and known inconclusive results retried after sbri.retry_seconds within the total
call budget. An operator may request --refresh; no refresh input is added to the
agent tool. Interrupted/uncertain claims do not replay. Ordinary execution/report
failures retain reasons/raw references and do not invalidate an otherwise complete
baseline; integrity/authority violations still block. Cache summary/canonical JSON
checksums detect altered evidence, not same-user authority attacks. Raw command
logs stay private. Backend and scanner identity hashes plus optional backend_version
label aid provenance; TTL does not prove external advisory/publication freshness.

Host background processes cannot be reliably quiesced by these SDK facilities.
A Git tree snapshot is immutable but does not establish host authority isolation.
Native command hook infrastructure may fail open; status still refuses product
success without trusted PASS/delivery. These limitations are not hidden by tests.

## Credentials, observation and verification

Keep existing credentials outside task/workspace files and prompts. Vertex ADC
preflight uses the current SDK Python/environment and >=300-second refreshed
tokens. Persistent ADC discovery remains a deployment concern; no keys are created.
Existing gh credentials are used only by the trusted delivery adapter, whose
normal path is now blocked before client/credential acquisition. Same-user terminal
access to those credentials is precisely the unsupported guarantee, not prevented
merely by this API separation.

SDK state is local, not automatically registered in Agent Server/Canvas. Browser
rendering remains unverified. Historical remote evidence/probes are preserved;
they were not repeated.

```bash
python3 -S -m unittest discover -s tests_native -v
# Installed SDK Python:
python -m unittest discover -s tests_native -v
python3 -S -m compileall -q native_remediation tests_native
git diff --check
```

The complete discovered suite includes P1 regressions and SDK-specific tests.
Historical remote Agent Server probes skip when that package is not installed;
no remote service is required. Actual native workspace/terminal/
persistence/Stop probes use safe temporary directories and no inference. Executable
Maven/OSV stand-ins and controlled pipeline outputs are not real toolchain or
remediation proof. SDK execute_command emits non-fatal ResourceWarnings; no SDK
patch was made. No model, real target build, target edit, network analysis or PR ran.
