# Autonomous OSS Vulnerability Remediation — local SDK operations

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
They were not exercised over the network by offline tests.

Optional SBRI/research references point to host scripts/docs, not container paths.
They remain evidence sources selected by the one native agent, never a required
SBRI stage or fixed Spring Boot upgrade strategy. No special capability framework
or bespoke ordinary-command tool was added.

## Trust limitation and fail-closed behavior

Trusted task/policy, preparation receipts, baseline/acceptance records, SDK
persistence, journals, claims and credentials live outside the agent repository.
Private files/locks protect against accidental edits/other users, not the same
host user. No agent tool grants direct acceptance/delivery operations; the
cycle_evidence tool records agent-authored data only. An unrestricted shell still
can access sibling files, HOME, credentials and processes. LocalWorkspace is not
a sandbox, cwd is not containment, and production security isolation is not claimed.

The mandatory guarantee that agent commands and repository builds cannot alter
trusted records or access delivery credentials is **not supported here**.
files.require_independent_authority() raises Blocked before normal model dispatch,
default real build/acceptance, and GitHub delivery (including reconciliation).
No model-cost authorization flag disables it. This prevents knowingly claiming
trusted independent acceptance in the unsupported environment.

Consequently normal live start/prepare/run/delivery are NOT ready to execute:
prepare initializes the idle SDK then refuses untrusted preparation before
clone/build; it cannot issue COMPLETE. SDK initialization alone is available without
inference. Safe temporary test fixtures explicitly inject known outputs/mock
the authority guard; these seams are not a deployment mechanism or an end-to-end
success. No new isolation infrastructure is introduced by this correction.

## Preserved lifecycle and interfaces

The implemented flow is:
1. Initialize/restore Conversation without inference.
2. Deterministically prepare the approved repository/base and collect baseline.
3. Issue preparation.json only on COMPLETE, bound to native conversation, task
   digest, repository, approved SHA/tree, baseline digest and completion time.
4. Recheck evidence/deadline/base/first-run workspace, then send_message/run.
5. One native agent investigates, selects strategies, edits, self-tests/reassesses.
6. Native Stop validates independently; deny with feedback or exact-tree PASS delivery.

These entry points preserve that flow, but remain subject to the security blocker:
```bash
python -m native_remediation check-task --task /private/approved-task.json
python -m native_remediation prepare --task /private/approved-task.json --state /private/new-task
python -m native_remediation start --task /private/approved-task.json --state /private/new-task --authorize-run-and-delivery
python -m native_remediation run --state /private/task --authorize-run-and-delivery
python -m native_remediation resume --state /private/task --reason "documented interruption" --authorize-run-and-delivery
python -m native_remediation status --state /private/task
python -m native_remediation doctor --state /private/task
python -m native_remediation reconcile-delivery --state /private/task
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
task_tracker is native. cycle_evidence takes structured intent before material
edits and honest outcome before Finish; those records never constitute acceptance.
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
may terminate natively without acceptance or PR. Only exact-tree independent PASS
can enter the retained draft delivery contract: authorized repository/base SHA,
commit parent/tree, create-only branch, exact open draft head/base checks, durable
claim and positive reconciliation; uncertain push/POST is never blindly repeated.
The local trust guard prevents actual delivery while independence is unestablished.

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
python3 -S -m unittest tests_native.test_product tests_native.test_local_execution -v
# Installed SDK Python:
python -m unittest tests_native.test_product tests_native.test_sdk_contract tests_native.test_local_execution -v
python3 -S -m compileall -q native_remediation tests_native
git diff --check
```

31 native-runtime tests and 24 stdlib tests pass. Actual native workspace/terminal/
persistence/Stop probes use safe temporary directories and no inference. Executable
Maven/OSV stand-ins and controlled pipeline outputs are not real toolchain or
remediation proof. SDK execute_command emits non-fatal ResourceWarnings; no SDK
patch was made. No model, real target build, target edit, network analysis or PR ran.
