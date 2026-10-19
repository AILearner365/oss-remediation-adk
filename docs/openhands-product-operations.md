# Native OpenHands remediation operations

The supported product entrypoint is `scripts/openhands_service.py start`.
It starts the published Canvas launcher and one local application control process.
Startup never creates smoke conversations or dispatches a model. Submission runs
repository preparation, Maven/OSV baseline, optional SBRI and idle native attachment;
execution and draft-PR delivery require separate, exact authorizations.

## Start and restart

Run from the integration repository on `openhands-service-integration`:

```bash
python3 scripts/openhands_service.py start
python3 scripts/openhands_service.py restart
```

Prerequisites: Linux Cloud Shell, Python 3.12+, `/usr/bin/python3` capable of
importing `openhands_shared.stop_hook`, Git, Java 21, Maven, `uvx`, and the approved
OSV Scanner 2.6.0 binary on PATH. The existing deterministic validator dependencies
must be available to system Python; startup verifies its import before launch.
Node >=24 is reused or the checksum-pinned official Linux x64 Node 24.13.0 archive
is provisioned under `/tmp`. Other platforms require an installed Node >=24.

The launcher reuses Canvas 1.27.1, Agent Server/SDK/tools/workspace 1.55.1,
Automation 1.19.3 and LiteLLM 1.105.1. Package downloads and shared uv/npm caches
live under `/tmp/openhands-native-poc-1271-server-1551` and can be restored after
Cloud Shell replaces its VM. No separate SDK environment is installed for the API.
Allow approximately 3 GiB of temporary space and at least 1.1 GiB of available
memory for first startup; Maven and SBRI require additional execution headroom.

Default output includes:

```text
status: PRODUCT_RUNNING
ui: http://127.0.0.1:8080
api: http://127.0.0.1:8080/v1/remediations
canvas: http://127.0.0.1:8091/
keyFile: ~/.openhands/oss-remediation/product/api-key.txt
```

Use Cloud Shell Web Preview on port 8080 for the remediation UI and port 8091
for native Canvas. Localhost conversation links work locally; in Cloud Shell,
open the same conversation path on the port-8091 preview URL. Do not expose the
loopback services directly to the public Internet. API requests require the
product bearer key; the UI keeps it in session storage for that browser tab.

Persistent home is `~/.openhands/oss-remediation/product`:

| Path | Purpose |
| --- | --- |
| `config.json` | Approved repositories/branches/commits, scanner path and execution limits |
| `tasks.sqlite3` | Immutable task contracts, stage evidence references, execution and delivery claims |
| `sources/`, `workspaces/` | Isolated Git sources and task worktrees |
| `artifacts/`, `hooks/` | Baseline, SBRI, validation evidence and stable independent hook configurations |
| `native/canvas/dev_conversations/` | Native conversation persistence and events |
| `native/` | Persistent Canvas encryption/session keys and native state |
| `product.log` | Private service diagnostics |

The default approved target is `AILearner365/maven-multimodule-app`,
`refs/heads/main-runrunning`, commit `9ea1b0ed5ca255db0fc7c659d050896d3ed5db78`.
The server checks the remote branch before preparing a workspace and fails if
it moved. An operator must review a new commit before changing `config.json`.
Additional repositories require explicit deployment configuration. `originUrl`
can select an operator-owned local mirror; it is never a public input field.

`--config /persistent/path/config.json` selects another deployment; configure
`stateDir` there. `--port` selects its product port. Default native ports are
8091/18910/18911/18912/19910; a foreign process or deployment on those ports is
refused. Two startup processes or workers cannot own the same deployment.

## Submit and observe

Use [the real-application payload](examples/real-app-remediation.json). It contains
the repository, base ref and approved SHA, objective, unchanged-Java/no-suppression
constraints, SBRI mode and draft delivery intent. Omit `expectedCommit` to use
the deployment-approved SHA. No database, interpreter, worker, conversation or
hook paths are accepted from API clients.

```bash
export REMEDIATION_URL=http://127.0.0.1:8080
export REMEDIATION_KEY_FILE="$HOME/.openhands/oss-remediation/product/api-key.txt"

curl --fail-with-body "$REMEDIATION_URL/v1/remediations" \
  -H "Authorization: Bearer $(cat "$REMEDIATION_KEY_FILE")" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: my-remediation-001' \
  --data-binary @docs/examples/real-app-remediation.json

python3 -m openhands_shared.cli submit docs/examples/real-app-remediation.json \
  --idempotency-key my-cli-remediation-001
python3 -m openhands_shared.cli list
python3 -m openhands_shared.cli status TASK_ID
python3 -m openhands_shared.cli events TASK_ID
python3 -m openhands_shared.cli reports TASK_ID
python3 -m openhands_shared.cli result TASK_ID
python3 -m openhands_shared.cli diff TASK_ID
python3 -m openhands_shared.cli artifact TASK_ID baseline-report
```

API submission returns HTTP 202, a stable `taskId` and `statusUrl`. Reuse the
same idempotency key and payload after a lost response. The CLI prints its
generated key before sending; use `--idempotency-key` when retrying. Changing
the payload under an existing key returns HTTP 409.

In the UI, enter the product key, repository, branch, objective and SBRI choice,
then Submit. The same backend performs all stages. The task list survives
restart; select a task to inspect activity, results, evidence and diff. Native
events are fetched from Agent Server, without copying their content into a
second history ledger. `/events?pageId=...` and CLI `events --page-id ...` use
native `next_page_id` cursors. Canvas remains the native conversation interface;
the small submission/evidence UI supplies the application-specific task contract
that generic Canvas chat does not provide. Do not send a second remediation
request or manually resume an accepted task through Canvas.

## Authorize execution and delivery

Execution is deliberately gated. Inspect `executionOffer` in task status. Save
that exact object as `execution-authorization.json` and, only after approving
the cost and task identity, send:

```bash
python3 -m openhands_shared.cli execute TASK_ID execution-authorization.json
```

The corresponding API is `POST /v1/remediations/TASK_ID/execute`. The UI displays
the same budget before confirmation. Default: `vertex_ai/gemini-2.5-flash`,
12 native iterations and two independent validation denials, in
`deutschebank-aipocs/us-central1`. These are iteration bounds, not a hard dollar
cap. Vertex ADC must already be available to the running native server.
Native tools, Skills and engineering guidance are unchanged. The independent
Stop Hook uses stable `/usr/bin/python3`; an expired interpreter, missing
dependency, changed model/budget/workspace or mismatched persisted hook blocks
dispatch. Never relax the check to resume an old conversation.

After native termination, a final PASS and matching validated Git tree establish
acceptance. Native `finished` alone does not. Failed checks feed back through
the native Stop Hook until the denial limit; terminal results distinguish
accepted, partial remediation, bounded failure, infrastructure error and
recovery required. Reports and artifacts remain available for every attempt.

Draft delivery is currently allowlisted to the real application and
`main-runrunning`. Set `GITHUB_TOKEN` in the operator environment before starting
the product, and configure an existing Git HTTPS credential helper for pushing
that repository. Neither the product token nor GitHub API token is passed to
the native launcher; delivery Git children do not inherit the GitHub API token.
This is a trusted local coding runner, not an adversarial same-UID sandbox:
host/ADC files must be protected through the deployment's isolation boundary.

```bash
python3 -m openhands_shared.cli delivery-plan TASK_ID
```

Review the exact base, branch, changed files and validated tree. Save an
authorization object containing `authorize: true`, `baseCommit`, `validatedTree`
and `branch` from that plan, then:

```bash
python3 -m openhands_shared.cli authorize-delivery TASK_ID delivery-authorization.json
python3 -m openhands_shared.cli delivery TASK_ID
```

These map to GET `/delivery-plan`, POST `/delivery`, and GET `/delivery` under
the task URL. The UI offers the same review and confirmation. Submission with
`delivery.mode=github_pr` is intent; it never authorizes a push by itself.
Delivery commits the accepted tree directly, preserving the validated workspace,
pushes only its task-owned branch and creates an open draft PR. The review plan includes every changed file in the accepted tree, including new
files, staged edits and agent-made local commits. Application source edits are
allowed, not just POMs.

## Recovery

Run `start` after a Cloud Shell restart, or `restart` for a service restart.
Use `list` or the UI; no task-ID reconstruction or conversation attachment is
needed for normal completed stages and idle conversations. Unclaimed execution
authorizations are gated again on restart. Claimed execution is observed and
never automatically redispatched. Interrupted preparation or context attachment
is marked `RECOVERY_REQUIRED` and retains all evidence.

```bash
python3 -m openhands_shared.cli reconcile TASK_ID
```

Reconciliation can verify an attached idle conversation, repair the link to an
already-persisted initial context event, attach after all deterministic stages
committed, or observe an existing execution claim. It never calls `/run`.
An interrupted build/scan with incomplete evidence, a missing native conversation,
an obsolete hook, or an unresolvable execution intent remains blocked for
inspection; there is no destructive automatic reset or evidence overwrite.

For interrupted delivery, review `delivery-plan` and reauthorize that exact
base/tree/branch. A durable commit intent is recorded before push. The retry
reconciles the existing branch and all-state PR query before creating anything.
Lost push or PR responses reuse the original commit/PR. A mismatched branch,
changed base, closed/non-draft/mismatched PR or changed validation tree blocks
delivery. The create-only Git lease requires a previously absent remote branch;
it cannot replace an existing branch. No code pushes to the base branch.

Monitor home disk usage: build `target/` output is disposable, while task state,
reports and native conversations are durable. The product does not automatically
delete evidence or old tasks. It processes deterministic preparation sequentially
and uses existing shared Maven dependencies; it does not install per-task SDKs.
Preparation and model dispatch require at least 256 MiB of free persistent space.
Execution authorization returns `INSUFFICIENT_STORAGE` below that threshold;
status and evidence remain readable. The acceptance environment was down to about
93 MiB free at handoff and needs additional headroom before another preparation
or an authorized model run. No unrelated operator data was deleted.

See [implementation and acceptance evidence](verification/openhands-product-20261019/report.md)
for the actual tested scope and remaining external acceptance gates.
