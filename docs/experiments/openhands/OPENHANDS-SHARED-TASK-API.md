# OpenHands shared task API — M2 Change 1

Status: implemented foundation. Date: 2026-10-16.

This is the task registration and observation boundary specified by
[OPENHANDS-SHARED-BACKEND-IMPLEMENTATION-PLAN.md](OPENHANDS-SHARED-BACKEND-IMPLEMENTATION-PLAN.md).
It does not start a worker, prepare a repository, invoke OpenHands, contact
Vertex AI, run Maven or a scanner, validate changes, or deliver them. All newly
registered tasks remain `QUEUED`. M2 Change 2 adds a separately invoked trusted
internal preparation operation documented in
[OPENHANDS-SHARED-PREPARATION.md](OPENHANDS-SHARED-PREPARATION.md); registration
does not call it.

## Run locally

The service uses only the Python standard library:

```bash
python -m openhands_shared --database /durable/state/openhands-tasks.sqlite3 \
  --host 127.0.0.1 --port 8080
```

The database path must be on durable storage in a deployed service. The command
starts only the registration/read API; there is no execution worker in Change
1.

## Endpoints

| Method | Path | Behavior |
| --- | --- | --- |
| `POST` | `/v1/tasks` | Validate and durably register one `QUEUED` task. Returns `201` when created, `200` for an identical idempotent replay, and `409` if the key is reused for a different request. |
| `GET` | `/v1/tasks/{taskId}` | Read task status and the distinct execution, validation, and delivery states. |
| `GET` | `/v1/tasks/{taskId}/events?after={sequence}` | Read append-only events in sequence order. `after` is optional. |
| `GET` | `/v1/tasks/{taskId}/artifacts` | Read immutable artifact metadata; artifact content is outside the SQLite rows. |
| `GET` | `/v1/tasks/{taskId}/result` | Read an accepted or terminal result, or return `404 result_not_ready`. |

There is deliberately no HTTP transition, execute, validate, artifact-write or
delivery endpoint in this change.

## Registration example

```http
POST /v1/tasks HTTP/1.1
Content-Type: application/json

{
  "contractVersion": "1",
  "idempotencyKey": "repo-123-cve-batch-20261016",
  "repository": {
    "url": "https://github.com/AILearner365/maven-multimodule-app.git",
    "baseRef": "refs/heads/main-runrunning",
    "expectedCommit": "0123456789abcdef0123456789abcdef01234567"
  },
  "objective": "Resolve the identified HIGH and CRITICAL dependency vulnerabilities.",
  "constraints": {
    "javaVersionUnchanged": true,
    "springBoot": {
      "allowPatch": true,
      "allowMinor": true,
      "allowMajor": false,
      "allowDowngrade": false
    },
    "prohibitSuppressions": true,
    "prohibitedNewSeverities": ["CRITICAL", "HIGH"]
  },
  "acceptance": {
    "buildCommands": ["mvn clean verify"],
    "severityScope": ["CRITICAL", "HIGH"]
  },
  "agent": {
    "profile": "gate2-dependency-remediation-v1",
    "modelProfile": "vertex-gemini-2-5-flash",
    "maxIterations": 250,
    "maxValidationDenials": 3
  },
  "intelligence": {"sbri": {"mode": "auto"}},
  "delivery": {"mode": "none"},
  "metadata": {"source": "rest"}
}
```

Created response:

```json
{
  "contractVersion": "1",
  "created": true,
  "task": {
    "contractVersion": "1",
    "taskId": "task_9c47b5ae23894a9eafdf23e17de9f684",
    "status": "QUEUED",
    "stage": "queued",
    "createdAt": "2026-10-16T14:00:00.000Z",
    "updatedAt": "2026-10-16T14:00:00.000Z",
    "openhands": {"executionStatus": "NOT_STARTED", "conversationId": null},
    "validation": {"status": "NOT_VALIDATED", "attempts": 0, "accepted": false},
    "delivery": {"status": "NOT_REQUESTED"},
    "links": {
      "self": "/v1/tasks/task_9c47b5ae23894a9eafdf23e17de9f684",
      "events": "/v1/tasks/task_9c47b5ae23894a9eafdf23e17de9f684/events",
      "artifacts": "/v1/tasks/task_9c47b5ae23894a9eafdf23e17de9f684/artifacts",
      "result": "/v1/tasks/task_9c47b5ae23894a9eafdf23e17de9f684/result"
    }
  }
}
```

The initial event response contains `task.registered` at sequence `1`.
Identical replay returns the same task id and `"created": false`. Raw
credentials, credential-shaped fields, arbitrary `env`/`environment` fields,
unknown fields, credential-bearing repository URLs, unsupported profiles, and
non-`none` delivery modes are rejected.

## Persistence and lifecycle invariants

SQLite schema version 6 retains these Change 1 tables:

- `tasks`: canonical request and hash, unique idempotency key, current product
  status, separate OpenHands/validation/delivery states, optional immutable
  result, and timestamps;
- `events`: append-only `(task_id, sequence)` primary key plus a globally unique
  event id;
- `artifacts`: immutable metadata keyed by `(task_id, artifact_id)`, with unique
  safe relative paths, content hash and size; and
- `schema_info`: the schema compatibility version.

Change 2 adds immutable `preparations` metadata through a tested in-place
schema migration; it does not change these HTTP response contracts.
Change 3 adds immutable `baseline_assessments` metadata and registers its
content-addressed evidence through the existing artifact endpoint. It adds no
public execution route and does not change task registration or read response
shapes.
Change 4 adds immutable `intelligence_assessments` metadata and SBRI evidence
through the same artifact endpoint. `AGENT_RUNNING` after intelligence means
only that the agent stage is pending; no conversation is created by this API.
Change 5 adds native conversation association and bounded event-link metadata.
The trusted internal operation is documented in
[OPENHANDS-SHARED-AGENT-SERVER.md](OPENHANDS-SHARED-AGENT-SERVER.md). Task
registration still cannot provision or run a conversation.
Change 6 adds durable `execution_claims` and `validation_attempts`. A trusted
internal worker may invoke the guarded native execution and Stop Hook adapter,
but no public execution endpoint was added and `POST /v1/tasks` remains
registration-only. See
[OPENHANDS-SHARED-VALIDATION.md](OPENHANDS-SHARED-VALIDATION.md).

SQLite foreign keys, WAL mode, `BEGIN IMMEDIATE` write transactions, and a busy
timeout support concurrent registration. Registration writes the task and its
first event atomically. Internal future-worker transitions update status and
append the next event in one transaction. Database close/reopen preserves all
identifiers and metadata.

The reserved lifecycle vocabulary is encoded but not driven by this service.
`OpenHands executionStatus=COMPLETED` does not imply acceptance. `ACCEPTED`
requires independent validation `PASSED`; `SUCCEEDED` additionally requires
delivery `COMPLETED`. This preserves the migration agreement's distinction
between agent termination, deterministic acceptance and delivery completion.
