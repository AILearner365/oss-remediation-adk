# M3 Change 7A — task-to-Canvas read-only smoke check

Status: **IMPLEMENTED CHECKER; LIVE CANVAS/END-TO-END INTEGRATION NOT YET VERIFIED.**

This small increment adds only `scripts/shared_task_canvas_smoke.py` and its offline tests. It neither creates tasks nor runs baseline/SBRI/OpenHands. The script consumes an **already provisioned**, idle shared task; it verifies product-to-native conversation identity through the existing Task API and pinned Agent Server, checks a visible effective Stop Hook and native events, and prints the Canvas route. It does not claim a browser proof.

## On the Cloud Shell host tomorrow

Update only the integration branch; keep frozen Gate-2 files untouched:

```bash
cd ~/oss-remediation-adk
git switch openhands-service-integration
git pull --ff-only origin openhands-service-integration
python -m unittest discover -s tests/integration -p 'test_shared_task_canvas_smoke.py' -v
```

The test uses mocked HTTP responses and does not call Maven, OSV, SBRI, OpenHands or any external service.

### 1. Start the existing read-only task API

Use **the same persisted SQLite file that owns the task**, on durable storage. In terminal A:

```bash
cd ~/oss-remediation-adk
python -m openhands_shared --database /durable/state/openhands-tasks.sqlite3 --host 127.0.0.1 --port 8080
```

Replace the example database path with your real configured path. This command does not start a worker.

### 2. Use an already prepared + provisioned idle task

You need a task ID from the **existing shared backend** with all of these conditions:
- Preparation, baseline, optional intelligence already recorded.
- `SharedOpenHandsRuntime.provision(task_id)` has completed.
- Task status is `AGENT_RUNNING`; product execution is `NOT_STARTED`.
- Native conversation remains `idle` with effective Stop Hook installed.

**This incremental script does not create such a fixture or invoke the pipeline automatically.** If none exists, the full submit-to-provision integration remains **NOT PROVEN**. Do not register an arbitrary task expecting it to auto-execute; `POST /v1/tasks` only creates `QUEUED`.

Inspect task status in terminal B:

```bash
TASK_ID='task_REPLACE_WITH_EXISTING_32_HEX_ID'
curl -fsS "http://127.0.0.1:8080/v1/tasks/$TASK_ID"
```

### 3. Connect to the SAME Agent Server instance Canvas uses

Ensure your native Agent Server is running with the persisted conversation state from that task. Use local URLs or approved port forwards:

```bash
TASK_API='http://127.0.0.1:8080'
AGENT_SERVER='http://127.0.0.1:8000'
CANVAS_ORIGIN='http://127.0.0.1:3000'
python scripts/shared_task_canvas_smoke.py \
  --task-api "$TASK_API" \
  --agent-server "$AGENT_SERVER" \
  --canvas "$CANVAS_ORIGIN" \
  --task-id "$TASK_ID"
```

Adjust ports to the deployed services. The check is read-only and does not invoke `/run`. It must produce `API_MAPPING_PASSED__CANVAS_BROWSER_NOT_PROVEN`, native status `idle`, product execution `NOT_STARTED`, and a `canvasUrl`.

The helper intentionally expects accessible local unauthenticated/port-forwarded APIs. It does not support credentials; do not put tokens or passwords in URLs or expose the local Task API publicly.

### 4. Actually verify Canvas in a browser

Open the emitted `canvasUrl`. Ensure Canvas is connected to the **same** Agent Server, not an unrelated Canvas-selected backend. Confirm:

1. The route opens the same native conversation ID as in the task API.
2. The initial registered task context is visible.
3. Native events are visible.
4. The conversation remains idle; no model or tool execution occurs.
5. Reopening after a controlled restart retains the same conversation ID and history.

Do not label Canvas **PROVEN** from just a URL, API response or source inspection. Record screenshots or a sanitized browser observation.

### 5. Decision and next implementation step

| Item | Current evidence |
| --- | --- |
| Local checker + fake HTTP tests | Implemented; run tests using command above |
| Existing Task API to native conversation mapping | Checker available; execute against real provisioned task |
| Native conversation from same backend | Requires running the checker on actual persisted services |
| Browser Canvas rendering | NOT PROVEN until browser check |
| Register → prepare → baseline → intelligence → provision from a single client | NOT IMPLEMENTED by this increment |
| Task submission/control directly inside Canvas | NOT IMPLEMENTED |
| Real model remediation + validation | Not tested here; requires separate authorization |

**Next bounded change:** add a small trusted fixture/worker driver that uses the existing M2 components end to end for a disposable task; wire a minimal task launch/control interface only after the Canvas smoke check. Keep the existing Gate-2 shell experiment unchanged. Do not add another workflow engine, database or Canvas fork.

## Safety

No existing `scripts/openhands/*` file was modified. This check never creates or resumes native execution, never contacts a model, and never delivers a PR. The compatibility gate and stop-hook fail-closed requirements remain authoritative.
