"""Product lifecycle: deterministic stages and one native conversation per task.

The job rows coordinate application work only. Native events stay on Agent Server.
An interrupted operation is inspected, never blindly replayed.
"""
from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import subprocess
import shutil
import sys
import threading
from uuid import uuid4

from .contracts import (ContractValidationError, TaskRequest, TaskStatus, ExecutionStatus,
    OpenHandsRuntimeRecord, OpenHandsRuntimeStatus, OpenHandsEventLink,
    ValidationAttemptState, ValidationOutcome, canonical_json, reject_sensitive_input, utc_now)
from .store import SQLiteTaskStore, IdempotencyConflictError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import openhands_native_remediation as bridge
import openhands_native_poc as native

PROFILE = "gate2-dependency-remediation-v1"
MODEL = "vertex_ai/gemini-2.5-flash"
BUILD = "mvn -B -ntp clean verify"
REAL_URL = "https://github.com/AILearner365/maven-multimodule-app.git"
REAL_REF = "refs/heads/main-runrunning"
REAL_SHA = "9ea1b0ed5ca255db0fc7c659d050896d3ed5db78"


class StorageCapacityError(RuntimeError):
    """Insufficient persistent storage; observation remains available."""


def git(*args: str) -> str:
    environment = {k: v for k, v in os.environ.items() if k not in {
        "GITHUB_TOKEN", "GH_TOKEN", "REMEDIATION_API_KEY", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"}}
    result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", *args],
        capture_output=True, text=True, timeout=180,
        env={**environment, "GIT_TERMINAL_PROMPT": "0"})
    if result.returncode:
        raise ValueError("Git operation failed (output withheld); check repository access")
    return result.stdout.strip()


def default_config(home: Path) -> dict:
    import shutil
    return {"stateDir": str(home), "scanner": shutil.which("osv-scanner") or "osv-scanner",
        "scannerVersion": "2.6.0", "model": MODEL, "maxIterations": 12,
        "maxValidationDenials": 2, "repositories": [{"url": REAL_URL,
            "baseRef": REAL_REF, "expectedCommit": REAL_SHA}]}


class Product:
    def __init__(self, config: dict, *, http=None):
        if config.get("model") != MODEL:
            raise ValueError("Only the approved Vertex model profile is supported")
        if type(config.get("maxIterations")) is not int or not 1 <= config["maxIterations"] <= 100:
            raise ValueError("maxIterations must be from 1 through 100")
        if type(config.get("maxValidationDenials")) is not int or not 0 <= config["maxValidationDenials"] <= 20:
            raise ValueError("maxValidationDenials must be from 0 through 20")
        self.config = config
        self.home = Path(config["stateDir"]).expanduser().resolve()
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.store = SQLiteTaskStore(self.home / "tasks.sqlite3")
        if http is None:
            native.configure_server_version("1.55.1")
        self.http = http or native.http
        self.wake = threading.Event()
        self.stopping = threading.Event()
        self.thread = None
        with self.db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS product_jobs (
                task_id TEXT PRIMARY KEY REFERENCES tasks(task_id), input_hash TEXT NOT NULL,
                phase TEXT NOT NULL, error_code TEXT, execution_authorized INTEGER NOT NULL DEFAULT 0,
                delivery_plan TEXT, updated_at TEXT NOT NULL)""")

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.store.database_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def job(self, task_id):
        self.store.get_status(task_id)
        with self.db() as db:
            row = db.execute("SELECT * FROM product_jobs WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            raise ValueError("Task is not managed by this product; use explicit legacy inspection")
        return dict(row)

    def phase(self, task_id, phase, error=None):
        with self.db() as db:
            db.execute("UPDATE product_jobs SET phase=?, error_code=?, updated_at=? WHERE task_id=?",
                (phase, error, utc_now(), task_id))

    def repository(self, url, ref):
        matches = [r for r in self.config["repositories"] if r["url"] == url and r["baseRef"] == ref]
        if len(matches) != 1:
            raise ContractValidationError("Repository and branch must be approved in product config")
        return matches[0]

    def submit(self, value, key):
        if not isinstance(value, dict):
            raise ContractValidationError("Submission must be a JSON object")
        reject_sensitive_input(value)
        if set(value) - {"repository", "objective", "constraints", "intelligence", "delivery"}:
            raise ContractValidationError("Unsupported public submission field")
        repo = value.get("repository", {})
        if not isinstance(repo, dict) or set(repo) - {"url", "baseRef", "expectedCommit"}:
            raise ContractValidationError("Invalid repository fields")
        approved = self.repository(repo.get("url"), repo.get("baseRef"))
        expected = repo.get("expectedCommit", approved["expectedCommit"])
        if expected != approved["expectedCommit"]:
            raise ContractValidationError("Commit differs from operator-approved target")
        constraints = {"javaVersionUnchanged": True, "prohibitSuppressions": True,
            "prohibitedNewSeverities": ["CRITICAL", "HIGH"], "springBoot": {
                "allowPatch": True, "allowMinor": True, "allowMajor": False, "allowDowngrade": False}}
        supplied = value.get("constraints", {})
        if not isinstance(supplied, dict) or set(supplied) - set(constraints):
            raise ContractValidationError("Invalid constraints")
        constraints.update(supplied)
        if constraints["javaVersionUnchanged"] is not True or constraints["prohibitSuppressions"] is not True:
            raise ContractValidationError("This deployment requires unchanged Java and prohibits suppressions")
        delivery = value.get("delivery", {"mode": "none"})
        if not isinstance(delivery, dict) or set(delivery) - {"mode", "draft"} or delivery.get("draft", True) is not True:
            raise ContractValidationError("Only draft delivery is supported")
        request = TaskRequest.from_dict({"contractVersion": "1", "idempotencyKey": key,
            "repository": {"url": repo["url"], "baseRef": repo["baseRef"], "expectedCommit": expected},
            "objective": value.get("objective"), "constraints": constraints,
            "acceptance": {"buildCommands": [BUILD], "severityScope": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]},
            "agent": {"profile": PROFILE, "modelProfile": "vertex-gemini-2-5-flash",
                "maxIterations": self.config["maxIterations"],
                "maxValidationDenials": self.config["maxValidationDenials"]},
            "intelligence": value.get("intelligence", {"sbri": {"mode": "auto"}}),
            "delivery": {"mode": delivery.get("mode")}, "metadata": {"source": "rest"}})
        registration = self.store.register_task(request)
        task_id = registration.status.task_id
        digest = hashlib.sha256(canonical_json(value).encode()).hexdigest()
        with self.db() as db:
            prior = db.execute("SELECT input_hash FROM product_jobs WHERE task_id=?", (task_id,)).fetchone()
            if prior and prior[0] != digest:
                raise IdempotencyConflictError(key, task_id)
            db.execute("INSERT OR IGNORE INTO product_jobs (task_id,input_hash,phase,updated_at) VALUES (?,?,?,?)",
                (task_id, digest, "QUEUED", utc_now()))
        self.wake.set()
        return {"taskId": task_id, "created": registration.created, "statusUrl": "/v1/remediations/" + task_id}

    def start(self):
        # A single service process owns this database (OS lock in server.py).
        # Mark uncertain work on restart. Native execution is only observed.
        with self.db() as db:
            db.execute("UPDATE product_jobs SET phase='RECOVERY_REQUIRED', error_code='SERVICE_INTERRUPTED' "
                "WHERE phase IN ('PREPARING','ATTACHING','DELIVERING')")
            db.execute("UPDATE product_jobs SET phase='OBSERVING' WHERE phase='DISPATCHING'")
            db.execute("UPDATE product_jobs SET phase='AWAITING_EXECUTION_AUTHORIZATION', execution_authorized=0, "
                "error_code='RESTART_REQUIRES_EXECUTION_AUTHORIZATION' WHERE phase='AUTHORIZED'")
            db.execute("UPDATE product_jobs SET phase='RECOVERY_REQUIRED', error_code='RESTART_REQUIRES_DELIVERY_AUTHORIZATION' "
                "WHERE phase='DELIVERY_AUTHORIZED'")
        self.thread = threading.Thread(target=self._work, name="remediation-worker", daemon=True)
        self.thread.start()

    def close(self):
        self.stopping.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=5)

    def _work(self):
        while not self.stopping.is_set():
            with self.db() as db:
                rows = db.execute("SELECT task_id,phase FROM product_jobs WHERE phase IN "
                    "('QUEUED','AUTHORIZED','OBSERVING','DELIVERY_AUTHORIZED') ORDER BY updated_at").fetchall()
            for row in rows:
                if self.stopping.is_set():
                    break
                try:
                    self.advance(row["task_id"], row["phase"])
                except Exception as exc:
                    # Exceptions can contain credentials, raw HTTP responses, or model data.
                    # Persist only the exception type and a deterministic recovery classification.
                    phase = self.job(row["task_id"])["phase"]
                    if phase == "BASELINE_NOT_ACTIONABLE":
                        continue
                    recovery = phase in {"ATTACHING", "DISPATCHING", "OBSERVING", "DELIVERING"}
                    self.phase(row["task_id"], "RECOVERY_REQUIRED" if recovery else "INFRASTRUCTURE_ERROR",
                        type(exc).__name__)
            self.wake.wait(3)
            self.wake.clear()

    def advance(self, task_id, phase):
        if phase == "QUEUED":
            self.phase(task_id, "PREPARING")
            self.prepare(task_id)
            self.phase(task_id, "ATTACHING")
            self.attach(task_id)
            self.phase(task_id, "AWAITING_EXECUTION_AUTHORIZATION")
        elif phase == "AUTHORIZED":
            self.phase(task_id, "DISPATCHING")
            self.check_capacity()
            self.require_server()
            bridge.dispatch_native_once(self.store, task_id, worker_id="product-" + task_id,
                request=self.native_request(task_id), http=self.http)
            self.phase(task_id, "OBSERVING")
        elif phase == "OBSERVING":
            self.observe(task_id)
        elif phase == "DELIVERY_AUTHORIZED":
            import openhands_pr_delivery as delivery
            self.phase(task_id, "DELIVERING")
            details = json.loads(self.job(task_id)["delivery_plan"])
            delivery.deliver(details, delivery.APPROVAL, os.environ.get("GITHUB_TOKEN", ""))
            self.phase(task_id, "DELIVERED")

    def hook(self, task_id):
        return self.home / "hooks" / (task_id + ".json")

    def prepare(self, task_id):
        from autonomous_oss_remediation_agent.config import MavenConfig, ScannerConfig
        from .preparation import TrustedRepository, PreparationConfig, DeterministicPreparer
        from .baseline import BaselineConfig, BaselineProfile, DeterministicBaselineAssessor
        from .intelligence import IntelligenceConfig, IntelligenceProfile, SharedIntelligenceAssessor
        self.check_capacity()
        request = self.store.get_request(task_id)
        approved = self.repository(request.repository.url, request.repository.base_ref)
        origin = approved.get("originUrl", approved["url"])
        remote = git("ls-remote", "--exit-code", origin, approved["baseRef"]).split()[0]
        if remote != request.repository.expected_commit:
            raise ValueError("Approved remote base moved; execution refused")
        # One isolated source per task avoids source mutation and shared index races.
        source = self.home / "sources" / task_id
        source.parent.mkdir(parents=True, exist_ok=True)
        if not source.exists():
            git("clone", "--no-checkout", "--", origin, str(source))
            git("-C", str(source), "checkout", "--detach", remote)
            with (source / ".git/info/exclude").open("a") as stream:
                stream.write("\n# Maven generated build directories\ntarget/\n")
        trusted = TrustedRepository(approved["url"], source, origin)
        DeterministicPreparer(self.store, PreparationConfig(self.home / "workspaces", (trusted,))).prepare(task_id)
        scanner_path = Path(self.config["scanner"]).resolve(strict=True)
        scanner = ScannerConfig(backend="osv", mode="configured", executable=str(scanner_path),
            version=self.config["scannerVersion"], sha256=hashlib.sha256(scanner_path.read_bytes()).hexdigest())
        artifacts = self.home / "artifacts"
        baseline = DeterministicBaselineAssessor(self.store, BaselineConfig(artifacts, (
            BaselineProfile(PROFILE, (BUILD,), MavenConfig(mode="system"), scanner),))).assess(task_id)
        if baseline.assessment_status.value != "COMPLETED":
            self.phase(task_id, "BASELINE_NOT_ACTIONABLE", baseline.assessment_status.value)
            raise ValueError("Baseline not actionable; inspect baseline report")
        intel = SharedIntelligenceAssessor(self.store, IntelligenceConfig(artifacts, (
            IntelligenceProfile("product-sbri-v1", PROFILE, ROOT, scanner=scanner_path, max_candidates=3),))).assess(task_id)
        if intel.outcome.value not in {"COMPLETE", "PARTIAL", "DISABLED", "NOT_APPLICABLE"}:
            raise ValueError("SBRI could not produce usable evidence")
        self.hook(task_id).parent.mkdir(parents=True, exist_ok=True)
        native.write_private(self.hook(task_id), json.dumps({"database": str(self.store.database_path),
            "artifactRoot": str(artifacts), "profiles": [{"profileId": PROFILE,
                "buildCommands": [BUILD], "maven": {"mode": "system"}, "scanner": scanner.to_dict()}]}))

    def native_request(self, task_id):
        return bridge.build_request(self.store, task_id, hook_config=self.hook(task_id),
            model=self.config["model"], max_iterations=self.store.get_request(task_id).agent.max_iterations)

    def attach(self, task_id):
        if self.store.get_openhands_runtime(task_id):
            raise ValueError("Existing runtime requires inspection, not replacement")
        self.require_server()
        request = self.store.get_request(task_id)
        prep = self.store.get_preparation(task_id)
        conversation = str(uuid4())
        fingerprint = hashlib.sha256((task_id + conversation + request.objective).encode()).hexdigest()
        self.store.record_openhands_runtime(OpenHandsRuntimeRecord(
            task_id=task_id, conversation_id=conversation, agent_server_identity="native-local-1551",
            agent_server_version="1.55.1", sdk_version="1.55.1", tools_version="1.55.1",
            agent_profile_id=PROFILE, native_agent_profile_id=str(uuid4()), native_agent_profile_revision=0,
            model_profile_id=request.agent.model_profile, native_model=self.config["model"],
            profile_fingerprint=fingerprint, request_fingerprint=fingerprint,
            workspace_path=prep.workspace_path, baseline_commit=prep.baseline_commit,
            runtime_status=OpenHandsRuntimeStatus.CONVERSATION_READY, execution_status=ExecutionStatus.NOT_STARTED,
            last_native_event_id=None, last_native_event_order=0, failure_code=None, failure_detail=None,
            created_at=utc_now(), updated_at=utc_now()))
        payload = self.native_request(task_id)
        bridge.create_idle_native_conversation(payload, self.http,
            initial_message=bridge.render_task_objective(self.store, task_id, hook_config=self.hook(task_id)))
        events = self.http("GET", f"/api/conversations/{conversation}/events/search?limit=100&sort_order=TIMESTAMP")
        messages = [e for e in events.get("items", []) if e.get("kind") == "MessageEvent" and e.get("id")]
        if len(messages) != 1:
            raise ValueError("Native context event is ambiguous")
        self.store.link_openhands_event(OpenHandsEventLink(task_id=task_id, conversation_id=conversation,
            native_event_id=messages[0]["id"], native_order=1, native_kind="MessageEvent",
            native_timestamp=None, observed_at=utc_now()), context_attached=True)

    def require_server(self):
        info = self.http("GET", "/server_info")
        if any(info.get(k) != "1.55.1" for k in ("version", "sdk_version", "tools_version")):
            raise ValueError("Native server/SDK/tools version mismatch")

    def check_capacity(self):
        if shutil.disk_usage(self.home).free < 256 * 1024 * 1024:
            raise StorageCapacityError("Persistent storage requires at least 256 MiB free; task and evidence retained")

    def authorize_execution(self, task_id, value):
        request = self.store.get_request(task_id)
        expected = {"expectedCommit": request.repository.expected_commit, "model": self.config["model"],
            "maxIterations": request.agent.max_iterations, "authorize": True}
        if value != expected:
            raise ContractValidationError("Explicit authorization must match task executionOffer exactly")
        self.check_capacity()
        with self.db() as db:
            if db.execute("UPDATE product_jobs SET phase='AUTHORIZED', execution_authorized=1 WHERE task_id=? "
                    "AND phase='AWAITING_EXECUTION_AUTHORIZATION'", (task_id,)).rowcount != 1:
                if self.job(task_id)["execution_authorized"]:
                    return self.status(task_id)
                raise ValueError("Task is not awaiting execution authorization")
        self.wake.set()
        return self.status(task_id)

    def observe(self, task_id):
        from .validation import SharedValidationService
        from .stop_hook import load_stop_hook_config
        runtime = self.store.get_openhands_runtime(task_id)
        claim = self.store.get_execution_claim(task_id)
        if not runtime or not claim:
            raise ValueError("No durable dispatch claim; do not replay")
        actual = self.http("GET", f"/api/conversations/{runtime.conversation_id}")
        state = actual.get("execution_status")
        if state in {"running", "finished"} and claim.dispatch_status.value != "DISPATCHED":
            self.store.update_execution_dispatch(task_id, dispatched=True)
        if state == "running":
            self.phase(task_id, "OBSERVING")
            return
        if state not in {"finished", "error", "stuck"}:
            raise ValueError("Uncertain native execution; manual inspection required")
        attempts = self.store.list_validation_attempts(task_id)
        if any(a.state is ValidationAttemptState.RUNNING for a in attempts):
            raise ValueError("Interrupted validation requires inspection")
        completed = [a for a in attempts if a.state is ValidationAttemptState.COMPLETED]
        _, config = load_stop_hook_config(self.hook(task_id))
        validator = SharedValidationService(self.store, config)
        if state == "finished" and not completed:
            validator.handle_stop(task_id, workspace_argument=runtime.workspace_path)
            completed = list(self.store.list_validation_attempts(task_id))
        if completed and completed[-1].outcome is ValidationOutcome.PASS:
            if not validator.verify_validated_state(task_id, completed[-1].attempt):
                raise ValueError("Final workspace differs from validated tree")
        self.store.record_native_execution_terminal(task_id, completed=state == "finished")
        status = self.store.get_status(task_id)
        self.phase(task_id, "ACCEPTED" if status.status is TaskStatus.ACCEPTED else
            "INFRASTRUCTURE_ERROR" if status.status is TaskStatus.FAILED_INFRASTRUCTURE else
            "PARTIAL_REMEDIATION" if completed and completed[-1].resolved_finding_count else "BOUNDED_FAILURE")

    def status(self, task_id):
        job = self.job(task_id)
        request = self.store.get_request(task_id)
        status = self.store.get_status(task_id).to_dict()
        status.update({"productPhase": job["phase"], "errorCode": job["error_code"],
            "repository": request.repository.to_dict(), "executionOffer": {
                "expectedCommit": request.repository.expected_commit, "model": self.config["model"],
                "maxIterations": request.agent.max_iterations, "authorize": True}})
        prefix = "/v1/remediations/" + task_id
        status["links"] = {name: prefix + suffix for name, suffix in {
            "self": "", "events": "/events", "reports": "/reports", "result": "/result",
            "diff": "/diff", "delivery": "/delivery"}.items()}
        runtime = self.store.get_openhands_runtime(task_id)
        if runtime:
            status["nativeConversationUrl"] = f"http://127.0.0.1:{native.INGRESS}/conversations/{runtime.conversation_id}"
        return status

    def tasks(self):
        with self.db() as db:
            ids = [r[0] for r in db.execute("SELECT task_id FROM product_jobs ORDER BY updated_at DESC LIMIT 100")]
        return [self.status(i) for i in ids]

    def reports(self, task_id):
        def serialized(record):
            return record.to_dict() if record else None
        return {"baseline": serialized(self.store.get_baseline(task_id)),
            "intelligence": serialized(self.store.get_intelligence(task_id)),
            "validationAttempts": [a.to_dict() for a in self.store.list_validation_attempts(task_id)],
            "artifacts": [a.to_dict() for a in self.store.list_artifacts(task_id)]}

    def artifact(self, task_id, artifact_id):
        items = [a for a in self.store.list_artifacts(task_id) if a.artifact_id == artifact_id]
        if len(items) != 1:
            raise ValueError("Artifact unavailable")
        item = items[0]
        root = (self.home / "artifacts").resolve()
        path = (root / item.relative_path).resolve(strict=True)
        if not path.is_relative_to(root) or item.size_bytes > 8 * 1024 * 1024:
            raise ValueError("Artifact exceeds safe path or response bounds")
        data = path.read_bytes()
        if len(data) != item.size_bytes or hashlib.sha256(data).hexdigest() != item.sha256:
            raise ValueError("Artifact integrity check failed")
        return {"artifact": item.to_dict(), "content": data.decode("utf-8")}

    def events(self, task_id, page_id=None):
        from urllib.parse import urlencode
        if page_id is not None and (not isinstance(page_id, str) or len(page_id) > 128):
            raise ContractValidationError("pageId exceeds native cursor bounds")
        runtime = self.store.get_openhands_runtime(task_id)
        query = {"limit": 50, "sort_order": "TIMESTAMP_DESC"}
        if page_id:
            query["page_id"] = page_id
        return {"workflow": [e.to_dict() for e in self.store.list_events(task_id)],
            "native": self.http("GET", f"/api/conversations/{runtime.conversation_id}/events/search?" + urlencode(query)) if runtime else None}

    def result(self, task_id):
        result = self.store.get_result(task_id)
        snapshot = self.store.get_status(task_id)
        if result is None and snapshot.status is TaskStatus.ACCEPTED and snapshot.execution_status is ExecutionStatus.COMPLETED:
            from .contracts import TaskResult, ResultOutcome, DeliveryStatus
            attempt = self.store.list_validation_attempts(task_id)[-1]
            runtime = self.store.get_openhands_runtime(task_id)
            result = TaskResult(task_id=task_id, outcome=ResultOutcome.ACCEPTED,
                execution_status=snapshot.execution_status, validation_status=snapshot.validation_status,
                delivery_status=DeliveryStatus.PENDING, baseline_commit=runtime.baseline_commit,
                validated_tree=attempt.validated_tree, validation_attempt=attempt.attempt,
                validation_report_artifact_id=attempt.report_artifact_id, conversation_id=runtime.conversation_id,
                artifact_ids=tuple(a.artifact_id for a in self.store.list_artifacts(task_id)),
                completed_at=attempt.completed_at)
        phase = self.job(task_id)["phase"]
        terminal = {"ACCEPTED", "DELIVERED", "INFRASTRUCTURE_ERROR", "RECOVERY_REQUIRED",
            "PARTIAL_REMEDIATION", "BOUNDED_FAILURE", "BASELINE_NOT_ACTIONABLE"}
        return {"task": self.status(task_id), "outcome": phase if phase in terminal else "PENDING",
            "result": result.to_dict() if result else None,
            "evidence": self.reports(task_id), "delivery": self.delivery_state(task_id)}

    def diff(self, task_id):
        prep = self.store.get_preparation(task_id)
        if not prep:
            return {"diff": ""}
        attempts = self.store.list_validation_attempts(task_id)
        tree = (attempts[-1].validated_tree if attempts and attempts[-1].outcome is ValidationOutcome.PASS
            and self.store.get_status(task_id).accepted else None)
        arguments = ["-C", prep.workspace_path, "diff", "--no-ext-diff", prep.baseline_commit]
        if tree:
            arguments.append(tree)
        result = git(*arguments, "--")
        return {"diff": result[:256000], "truncated": len(result) > 256000, "validatedTree": tree}

    def delivery_state(self, task_id):
        self.job(task_id)
        with self.db() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='openhands_delivery_claims'").fetchone():
                return None
            row = db.execute("SELECT * FROM openhands_delivery_claims WHERE task_id=?", (task_id,)).fetchone()
        return dict(row) if row else None

    def delivery_plan(self, task_id):
        import openhands_pr_delivery as delivery
        job = self.job(task_id)
        if job["delivery_plan"] and self.delivery_state(task_id):
            return json.loads(job["delivery_plan"])
        request = self.store.get_request(task_id)
        details = delivery.plan(task_id, self.hook(task_id), expected_base=request.repository.expected_commit)
        details["hookConfig"] = str(self.hook(task_id))
        return details

    def authorize_delivery(self, task_id, value):
        import openhands_pr_delivery as delivery
        job = self.job(task_id)
        if job["phase"] == "DELIVERED":
            return self.result(task_id)
        # Recovery reuses the immutable approved plan, then reconciles GitHub.
        existing = self.delivery_state(task_id)
        details = json.loads(job["delivery_plan"]) if existing else self.delivery_plan(task_id)
        if value != {"authorize": True, "baseCommit": details["baseCommit"],
                "validatedTree": details["validatedTree"], "branch": details["branch"]}:
            raise ContractValidationError("Authorization must identify exact delivery plan base/tree/branch")
        if not os.environ.get("GITHUB_TOKEN"):
            raise ValueError("Server GITHUB_TOKEN is required for authorized delivery")
        with self.db() as db:
            changed = db.execute("UPDATE product_jobs SET phase='DELIVERY_AUTHORIZED', delivery_plan=? WHERE task_id=? "
                "AND phase IN ('ACCEPTED','RECOVERY_REQUIRED')", (canonical_json(details), task_id)).rowcount
        if not changed and job["phase"] not in {"DELIVERY_AUTHORIZED", "DELIVERING"}:
            raise ValueError("Task is not ready for delivery")
        self.wake.set()
        return self.status(task_id)

    def reconcile(self, task_id):
        job = self.job(task_id)
        if job["phase"] != "RECOVERY_REQUIRED":
            return self.status(task_id)
        if self.delivery_state(task_id):
            return self.status(task_id)  # Explicit delivery authorization retries reconciliation.
        if self.store.get_execution_claim(task_id):
            self.observe(task_id)
            return self.status(task_id)
        runtime = self.store.get_openhands_runtime(task_id)
        if runtime is None and self.store.get_baseline(task_id) and self.store.get_intelligence(task_id) and self.hook(task_id).is_file():
            # All expensive stages are committed. No runtime means attach()
            # could not have issued a native mutation (association is first).
            self.phase(task_id, "ATTACHING")
            try:
                self.attach(task_id)
            except Exception:
                self.phase(task_id, "RECOVERY_REQUIRED", "CONTEXT_ATTACHMENT_INCOMPLETE")
                raise
            self.phase(task_id, "AWAITING_EXECUTION_AUTHORIZATION")
            return self.status(task_id)
        if runtime and runtime.runtime_status is OpenHandsRuntimeStatus.CONTEXT_ATTACHED:
            bridge.validate_native_response(self.http("GET", f"/api/conversations/{runtime.conversation_id}?include_skills=true"),
                self.native_request(task_id))
            self.phase(task_id, "AWAITING_EXECUTION_AUTHORIZATION")
            return self.status(task_id)
        if runtime and runtime.runtime_status is OpenHandsRuntimeStatus.CONVERSATION_READY:
            payload = self.native_request(task_id)
            bridge.validate_native_response(self.http("GET", f"/api/conversations/{runtime.conversation_id}?include_skills=true"), payload)
            events = self.http("GET", f"/api/conversations/{runtime.conversation_id}/events/search?limit=100&sort_order=TIMESTAMP")
            messages = [e for e in events.get("items", []) if e.get("kind") == "MessageEvent" and e.get("id")]
            if len(messages) != 1:
                raise ValueError("Uncertain native context requires inspection")
            expected = bridge.render_task_objective(self.store, task_id, hook_config=self.hook(task_id))
            if expected not in canonical_json(messages[0]):
                # JSON escaping prevents substring checks; inspect text blocks.
                content = messages[0].get("llm_message", messages[0]).get("content", [])
                if not any(c.get("type") == "text" and c.get("text") == expected for c in content):
                    raise ValueError("Persisted native context does not match task objective")
            self.store.link_openhands_event(OpenHandsEventLink(task_id=task_id, conversation_id=runtime.conversation_id,
                native_event_id=messages[0]["id"], native_order=1, native_kind="MessageEvent",
                native_timestamp=None, observed_at=utc_now()), context_attached=True)
            self.phase(task_id, "AWAITING_EXECUTION_AUTHORIZATION")
            return self.status(task_id)
        raise ValueError("Interrupted preparation or context attachment requires evidence inspection; task retained")
