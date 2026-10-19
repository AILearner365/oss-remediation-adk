# Proven native OpenHands one-file smoke

On 2026-10-19 one native run produced [draft PR #214](https://github.com/AILearner365/maven-multimodule-app/pull/214)
without the custom product server, API, UI, CLI, SQLite or lifecycle coordinator.
This is a one-file feasibility result, not proof of vulnerability remediation.
The sanitized [execution evidence](evidence/native-wiring-20261019.json) is the
authoritative summary; earlier historical experiments remain intact.

## Verified execution

| Item | Observed result |
| --- | --- |
| Conversation | `05f7716a-90bc-4ec5-a90e-01b7a4de5fa0`, native `finished` |
| Runtime | Canvas 1.27.1; Agent Server/SDK/tools 1.55.1; LiteLLM 1.105.1 |
| Model | `vertex_ai/gemini-2.5-flash`, three-iteration budget, retries disabled |
| Usage | One run, two model responses, 9,876 prompt / 297 completion tokens; 205 reasoning tokens reported; native reported cost $0.0037053 |
| Agent actions | One terminal file write, then FinishTool |
| Independent validation | PASS, one regular non-executable added file, exact contents and no other diff |
| Base | `main-runrunning` at `9ea1b0ed5ca255db0fc7c659d050896d3ed5db78` |
| Validated tree | `ec81f52dbaf259cf02ccc485a0c8a2150bca38e0` |
| Delivery commit | `faad2a0a8845b4217c10cbf6cc71cdf4ae80dc8f`, remote tree and parent verified |
| Branch | `openhands/native-wiring-05f7716a-90bc-4ec5-a90e-01b7a4de5fa0` |
| Stop Hook | One invocation, exit 0, explicit allow only after draft PR confirmation |
| Visibility | Same finished conversation through native API and Canvas API; browser activity unverified |

The only target change was a new `100644` file:

```diff
--- /dev/null
+++ b/openhands-native-wiring-test.txt
@@ -0,0 +1 @@
+Native OpenHands wiring test passed.
```

The file ends with one newline. No POM/application edits or base-branch push
occurred. SBRI's existing `python3 sbri --help` succeeded; no analysis ran.

## Minimal retained path

1. Reuse the official native installation through `openhands_native_poc.py`
   (1.55.1 configuration, API transport, Canvas readiness). For native-only
   persistent startup use `python3 scripts/openhands_service.py serve`; **not**
   its `start` action, which starts the custom product. No startup is required
   while the verified native stack is already healthy.
2. `scripts/openhands_native_wiring_submit.py` creates one native conversation
   bound to a clean isolated worktree and an explicit current approved base SHA.
   It sends the task with `run: false`, verifies effective hooks, then optionally
   dispatches once with `--execute`. Default behavior remains idle.
3. `scripts/openhands_native_wiring_hook.py` validates independently, writes
   conversation/base/tree-bound PASS evidence, snapshots the accepted Git tree,
   delivers through Git and GitHub REST using existing `gh` credentials, then
   returns allow only for the exact open draft PR. All other handled outcomes
   return deny. It has no product imports or database.

The successful hook initially imported Git/API/commit helpers from
`openhands_pr_delivery.py`. The retained hook includes only their stdlib Git,
REST and commit-tree behavior so importing the native path no longer loads
product audit/lifecycle modules. It preserves destination and create-only push
guards and adds explicit contract/event/claim identity and snapshot blob checks.
The commit message now describes a wiring test rather than Maven remediation.
These consolidation changes have offline verification only; no second live run.

### Native lazy initialization

`StartConversationRequest.hook_config` is supported. Server creation persists it
in native `meta.json` and passes it to `LocalConversation`. The SDK initially
keeps `_pending_hook_config`; the first message initializes the hook processor
and persists effective hooks into `base_state.json`. GET reflects runtime state,
so **initial `hook_config: null` is not evidence of rejection**. Send the task
with `run: false`, then check effective hooks before `/run`. Do not edit native
state files or add workspace hooks as a workaround.

### Reproduction prerequisites and explicit dispatch

Do not replay the verified conversation, branch or claims. The commands below
are for a separately authorized future smoke, not this consolidation task.

- Reuse pinned native services; verify `/server_info`, ADC, `gh` repository push
  access, and Git's existing HTTPS credential helper before dispatch.
- Refresh ADC with the native server's Python executable **and inherited
  environment**, using `scripts/openhands/vertex-adc-preflight.py
  --expected-project deutschebank-aipocs`. Require PASS and the unchanged
  300-second lifetime threshold. CLI token success alone is insufficient.
- Resolve `refs/heads/main-runrunning` again. Stop if it differs from the
  separately approved SHA; do not silently approve a new base.
- Use `git worktree add --detach <new-workspace> <approved-sha>` from an existing
  checkout of `https://github.com/AILearner365/maven-multimodule-app.git`.
- Choose a new private state directory outside that worktree, preferably under
  persistent home. Never delete/reuse a claimed state directory to retry.

After those checks and explicit paid-run/delivery authorization:

```bash
python3 scripts/openhands_native_wiring_submit.py \
  --workspace /absolute/new-isolated-worktree \
  --state-dir /absolute/new-private-evidence-directory \
  --expected-base <explicitly-approved-current-40-hex-sha> \
  --execute
```

This submits once and exits; OpenHands runs the agent and Stop command. Inspect
the native conversation/events and `validation.json`, `delivery-claim.json`,
`hook-invocations.jsonl` through read-only checks. There is no watcher. If any
create/run response is uncertain, inspect the claimed conversation; never rerun
the submitter or create another identity as a retry.

## Remaining limitations

- **ADC is temporary.** The server inherited a different `CLOUDSDK_CONFIG`
  directory from the terminal and fell back to metadata credentials. Referencing
  the refreshed user ADC through a symlink at the server's expected discovery
  path fixed refresh without copying credentials or restarting services. Both
  paths are temporary. For persistence, create user ADC directly in a private
  persistent directory and explicitly set `GOOGLE_APPLICATION_CREDENTIALS` when
  launching native services. No credential files, symlink targets, keys or native
  auth-bearing state files belong in Git. No service-account keys are needed.
- **Claims are local files.** An exclusive hook lock and per-conversation state
  precede remote mutations. Push is create-only; branch SHA and PR identity are
  reconciled remotely. After an uncertain POST with no positively found PR,
  completion blocks rather than blindly posting again. Lost claims, abrupt
  filesystem loss, multi-host operation and production durability are not proven.
- **Stop precedes final acceptance.** The SDK calls Stop after the agent sets
  FINISHED but before accepting termination. Delivery happens inside that gate,
  after independent PASS; the observed hook then allowed completion. Native
  `finished` alone is never a delivery authorization. Native hook infrastructure
  can fail open on command errors; missing PASS/delivery evidence is not success.
- **Browser activity is unverified.** Chromium reached Canvas but displayed
  onboarding/preferences. The API confirmed the conversation and finished status;
  that does not establish browser rendering of its activity.
- **Not production isolation or remediation.** Hook and agent share an OS user.
  Maven/OSV acceptance, scanner failures, SBRI policy, hostile-agent isolation and
  recovery under arbitrary failures are outside this one-file proof.

## Existing components bypassed, not removed

`openhands_shared/server.py`, `product.py`, `cli.py`, the product UI, SQLite task
store/lifecycle/event mirrors, `openhands_shared/openhands_runtime.py`, and
`scripts/openhands_real_workflow.py` are unnecessary for this native smoke.
The product-backed entry point in `openhands_pr_delivery.py` is also bypassed.
They remain intact for existing consumers and historical evidence. Independent
Maven/OSV validation, baseline preparation and optional SBRI remain domain
capabilities to retain for real remediation; this smoke does not replace them.

## Offline verification and smallest next step

```bash
python3 -S -m unittest discover -s tests/integration -p test_openhands_native_wiring.py -v
python3 -S scripts/openhands_native_wiring_submit.py --help
git diff --check
```

The checks use local Git fixtures and no model/server/GitHub calls. They cover
exact-tree validation, rejected extra/content/mode changes, conversation mismatch,
delivery commit tree/parent, native request limits and committed evidence linkage.

Next: define and review **one bounded real-remediation acceptance contract** on
an approved current base, reusing existing Maven/OSV baseline and deterministic
validator scripts. Bind its PASS to the same native conversation/base/tree before
adapting this thin Stop boundary. Do not simply relax the one-file allowlist.
