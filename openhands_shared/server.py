"""Authenticated REST and minimal submission UI for the shared product workflow."""
from __future__ import annotations
import argparse
import fcntl
import hmac
import json
import os
from pathlib import Path
import re
from urllib.parse import parse_qs, unquote
from wsgiref.simple_server import make_server

from .api import TaskApi
from .contracts import ContractValidationError
from .store import TaskNotFoundError, IdempotencyConflictError
from .product import Product, StorageCapacityError, native

TASK = re.compile(r"^/v1/remediations/(task_[0-9a-f]{32})(?:/(.*))?$")


class ProductApi:
    def __init__(self, product, token):
        if len(token.strip()) < 40:
            raise ValueError("A private product API key is required")
        self.product, self.token = product, token.strip()

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path == "/" and environ.get("REQUEST_METHOD") == "GET":
            data = Path(__file__).with_name("ui.html").read_bytes()
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8"),
                ("Content-Length", str(len(data))), ("Cache-Control", "no-store"),
                ("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"),
                ("X-Content-Type-Options", "nosniff")])
            return [data]
        supplied = environ.get("HTTP_AUTHORIZATION", "")
        if not hmac.compare_digest(supplied, "Bearer " + self.token):
            status, result = "401 Unauthorized", {"error": "Bearer authentication required"}
        else:
            try:
                status, result = self.dispatch(environ)
            except TaskNotFoundError:
                status, result = "404 Not Found", {"error": "Task not found"}
            except IdempotencyConflictError as exc:
                status, result = "409 Conflict", {"error": "Idempotency key conflicts", "taskId": exc.task_id}
            except StorageCapacityError as exc:
                status, result = "409 Conflict", {"error": str(exc), "code": "INSUFFICIENT_STORAGE"}
            except (ContractValidationError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                status, result = "400 Bad Request", {"error": str(exc)[:300]}
            except (ValueError, RuntimeError):
                status, result = "409 Conflict", {"error": "Operation blocked; inspect task phase, evidence and prerequisites"}
            except Exception:
                status, result = "503 Service Unavailable", {"error": "Dependency unavailable; task and evidence retained"}
        data = json.dumps(result, ensure_ascii=False).encode()
        start_response(status, [("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(data))), ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff")])
        return [data]

    def dispatch(self, env):
        method, path = env.get("REQUEST_METHOD", "GET"), env.get("PATH_INFO", "")
        product = self.product
        if path == "/health" and method == "GET":
            info = product.http("GET", "/server_info")
            return "200 OK", {"status": "ready", "nativeVersion": info.get("version"), "nativeOwnsExecution": True}
        if path == "/v1/remediations":
            if method == "GET":
                return "200 OK", {"tasks": product.tasks()}
            if method == "POST":
                key = env.get("HTTP_IDEMPOTENCY_KEY")
                if not key:
                    raise ContractValidationError("Idempotency-Key header is required")
                return "202 Accepted", product.submit(TaskApi._read_json(env), key)
        match = TASK.fullmatch(path)
        if not match:
            return "404 Not Found", {"error": "Route not found"}
        task, resource = match.groups()
        product.job(task)
        if method == "GET":
            readers = {None: product.status, "result": product.result, "reports": product.reports,
                "diff": product.diff, "delivery": product.delivery_state, "delivery-plan": product.delivery_plan}
            if resource in readers:
                return "200 OK", readers[resource](task)
            if resource == "events":
                query = parse_qs(env.get("QUERY_STRING", ""), strict_parsing=True)
                if set(query) - {"pageId"}:
                    raise ContractValidationError("Only pageId query is supported")
                return "200 OK", product.events(task, query.get("pageId", [None])[0])
            if resource and resource.startswith("artifacts/"):
                return "200 OK", product.artifact(task, unquote(resource[len("artifacts/"):]))
        if method == "POST":
            value = TaskApi._read_json(env)
            if resource == "execute":
                return "202 Accepted", product.authorize_execution(task, value)
            if resource == "delivery":
                return "202 Accepted", product.authorize_delivery(task, value)
            if resource == "reconcile" and value == {}:
                return "200 OK", product.reconcile(task)
        return "405 Method Not Allowed", {"error": "Unsupported method or resource"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    home = Path(config["stateDir"]).expanduser().resolve()
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Lifetime lock prevents two workers claiming the same queued preparation.
    with (home / "product.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        native.configure_server_version("1.55.1")
        product = Product(config)
        token = (home / "api-key.txt").read_text().strip()
        with make_server("127.0.0.1", args.port, ProductApi(product, token)) as server:
            product.start()
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                product.close()


if __name__ == "__main__":
    main()
