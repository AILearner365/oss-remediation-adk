"""Dependency-free REST/WSGI facade for M2 Change 1 task metadata.

POST registers a queued task only.  There is intentionally no worker startup,
OpenHands import, subprocess call, or lifecycle-transition HTTP endpoint here.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from typing import Any, Callable, Iterator
from wsgiref.simple_server import WSGIServer, make_server

from .contracts import CONTRACT_VERSION, ContractValidationError, TaskRequest
from .store import IdempotencyConflictError, SQLiteTaskStore, TaskNotFoundError


MAX_REQUEST_BYTES = 256 * 1024
TASK_PATH = re.compile(r"^/v1/tasks/(?P<task_id>task_[0-9a-f]{32})(?:/(?P<resource>events|artifacts|result))?$")


class TaskApi:
    """Small WSGI application exposing task registration and read endpoints."""

    def __init__(self, store: SQLiteTaskStore):
        self.store = store

    def __call__(self, environ: dict[str, Any], start_response: Callable[..., Any]) -> list[bytes]:
        try:
            status, body = self._dispatch(environ)
        except ContractValidationError as exc:
            status, body = "400 Bad Request", self._error("invalid_request", str(exc))
        except IdempotencyConflictError as exc:
            status, body = "409 Conflict", self._error(
                "idempotency_conflict",
                str(exc),
                taskId=exc.task_id,
            )
        except TaskNotFoundError as exc:
            status, body = "404 Not Found", self._error("task_not_found", str(exc))
        except (json.JSONDecodeError, UnicodeDecodeError):
            status, body = "400 Bad Request", self._error("invalid_json", "request body must be valid UTF-8 JSON")
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        start_response(
            status,
            [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(encoded))),
                ("Cache-Control", "no-store"),
            ],
        )
        return [encoded]

    def _dispatch(self, environ: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = str(environ.get("PATH_INFO", ""))
        if path == "/v1/tasks":
            if method != "POST":
                return "405 Method Not Allowed", self._error("method_not_allowed", "use POST for /v1/tasks")
            request = TaskRequest.from_dict(self._read_json(environ))
            registration = self.store.register_task(request)
            return ("201 Created" if registration.created else "200 OK"), {
                "contractVersion": CONTRACT_VERSION,
                "created": registration.created,
                "task": registration.status.to_dict(),
            }

        match = TASK_PATH.fullmatch(path)
        if match is None:
            return "404 Not Found", self._error("route_not_found", "route was not found")
        if method != "GET":
            return "405 Method Not Allowed", self._error("method_not_allowed", "task resources are read-only")

        task_id = match.group("task_id")
        resource = match.group("resource")
        if resource is None:
            return "200 OK", self.store.get_status(task_id).to_dict()
        if resource == "events":
            after = self._after_sequence(environ.get("QUERY_STRING", ""))
            events = self.store.list_events(task_id, after_sequence=after)
            return "200 OK", {
                "contractVersion": CONTRACT_VERSION,
                "taskId": task_id,
                "events": [event.to_dict() for event in events],
            }
        if resource == "artifacts":
            artifacts = self.store.list_artifacts(task_id)
            return "200 OK", {
                "contractVersion": CONTRACT_VERSION,
                "taskId": task_id,
                "artifacts": [artifact.to_dict() for artifact in artifacts],
            }
        result = self.store.get_result(task_id)
        if result is None:
            return "404 Not Found", self._error("result_not_ready", "task has no final or accepted result", taskId=task_id)
        return "200 OK", result.to_dict()

    @staticmethod
    def _read_json(environ: dict[str, Any]) -> Any:
        content_type = str(environ.get("CONTENT_TYPE", "")).split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise ContractValidationError("Content-Type must be application/json")
        raw_length = environ.get("CONTENT_LENGTH", "")
        try:
            length = int(raw_length)
        except (TypeError, ValueError) as exc:
            raise ContractValidationError("Content-Length must be present and numeric") from exc
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise ContractValidationError(f"request body must contain 1 through {MAX_REQUEST_BYTES} bytes")
        stream = environ.get("wsgi.input")
        if stream is None:
            raise ContractValidationError("request body is unavailable")
        payload = stream.read(length)
        if len(payload) != length:
            raise ContractValidationError("request body ended before Content-Length")
        return json.loads(payload.decode("utf-8"))

    @staticmethod
    def _after_sequence(query: str) -> int:
        if not query:
            return 0
        parts = query.split("&")
        if len(parts) != 1 or not parts[0].startswith("after="):
            raise ContractValidationError("events query supports only after=<non-negative integer>")
        value = parts[0][len("after=") :]
        if not value.isdigit():
            raise ContractValidationError("events after value must be a non-negative integer")
        return int(value)

    @staticmethod
    def _error(code: str, message: str, **details: Any) -> dict[str, Any]:
        error: dict[str, Any] = {"code": code, "message": message}
        error.update(details)
        return {"contractVersion": CONTRACT_VERSION, "error": error}


@contextmanager
def serve_task_api(
    store: SQLiteTaskStore,
    host: str = "127.0.0.1",
    port: int = 0,
) -> Iterator[WSGIServer]:
    """Create a local WSGI server context without starting a background worker."""

    server = make_server(host, port, TaskApi(store))
    try:
        yield server
    finally:
        server.server_close()
