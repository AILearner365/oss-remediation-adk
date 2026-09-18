from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import urlparse

from ..capabilities.execution import ProcessRunner
from ..config import DeliveryConfig, RemediationRequest
from ..deterministic.git_auth import (
    EnvironmentGitCredentialProvider as EnvironmentCredentialProvider,
    GitCredential as DeliveryCredential,
    NonInteractiveGitAuth,
)
from ..models import DeliveryPreflight, DeliveryResult, RepositoryBaseline, ValidationReport
from ..workspace import RunWorkspace, TraceStore, sha256_file

class DeliveryCredentialProvider(Protocol):
    def isolation_status(self) -> tuple[bool, str]: ...

    def resolve(self) -> DeliveryCredential: ...


class CallableCredentialProvider:
    def __init__(
        self,
        resolver: Callable[[], DeliveryCredential],
        *,
        isolated_from_agent: bool,
        description: str,
    ):
        self._resolver = resolver
        self._isolated = isolated_from_agent
        self._description = description

    def isolation_status(self) -> tuple[bool, str]:
        return self._isolated, self._description

    def resolve(self) -> DeliveryCredential:
        if not self._isolated:
            raise RuntimeError("Credential provider is accessible to the remediation identity")
        return self._resolver()


@dataclass(frozen=True)
class DeliveryContext:
    request: RemediationRequest
    workspace: RunWorkspace
    baseline: RepositoryBaseline
    validation: ValidationReport
    agent_summary: str


class DeliveryAdapter(Protocol):
    name: str

    def preflight(self, request: RemediationRequest) -> DeliveryPreflight: ...

    def deliver(self, context: DeliveryContext) -> DeliveryResult: ...


class ManualDeliveryAdapter:
    name = "manual"

    def preflight(self, request: RemediationRequest) -> DeliveryPreflight:
        return DeliveryPreflight(False, self.name, "Automated delivery is not configured")

    def deliver(self, context: DeliveryContext) -> DeliveryResult:
        return DeliveryResult(
            False,
            "VALIDATED_MANUAL_DELIVERY_REQUIRED",
            reason="Automated delivery is disabled; validated artifacts are retained for manual delivery",
        )


def configured_delivery_adapter(
    request: RemediationRequest,
    process_runner: ProcessRunner,
    trace: TraceStore,
    environment: dict[str, str] | None = None,
) -> DeliveryAdapter:
    if request.delivery.mode.lower() != "auto":
        return ManualDeliveryAdapter()
    adapter = request.delivery.adapter.lower()
    if adapter not in {"github", "github-rest", "git+github-rest"}:
        return ManualDeliveryAdapter()
    return GitHubRestDeliveryAdapter(
        request.delivery,
        EnvironmentCredentialProvider(environment),
        process_runner,
        trace,
    )


class GitHubRestDeliveryAdapter:
    name = "git+github-rest"

    def __init__(
        self,
        config: DeliveryConfig,
        credential_provider: DeliveryCredentialProvider,
        process_runner: ProcessRunner,
        trace: TraceStore,
        http_post: Callable[..., Any] | None = None,
    ):
        self.config = config
        self.credential_provider = credential_provider
        self.process_runner = process_runner
        self.trace = trace
        self.http_post = http_post

    def preflight(self, request: RemediationRequest) -> DeliveryPreflight:
        if request.delivery.mode != "auto":
            return DeliveryPreflight(False, self.name, "Request selected validation-only/manual delivery mode")
        isolated, reason = self.credential_provider.isolation_status()
        if not isolated:
            return DeliveryPreflight(False, self.name, f"Credential isolation unavailable: {reason}")
        if not _github_repository_name(request.repository_url):
            return DeliveryPreflight(False, self.name, "Repository URL is not a supported GitHub remote")
        return DeliveryPreflight(True, self.name, "Adapter and isolated credential provider are configured")

    def deliver(self, context: DeliveryContext) -> DeliveryResult:
        preflight = self.preflight(context.request)
        if not preflight.eligible:
            return DeliveryResult(False, "VALIDATED_MANUAL_DELIVERY_REQUIRED", reason=preflight.reason)
        actual_digest = digest_changed_paths(context.workspace.repository, context.validation.changed_files)
        if actual_digest != context.validation.tree_digest:
            return DeliveryResult(False, "DELIVERY_ABORTED", reason="Validated tree digest changed before delivery")
        if not context.validation.passed:
            return DeliveryResult(False, "DELIVERY_ABORTED", reason="Deterministic validation did not pass")
        if not context.validation.delivery_eligible:
            return DeliveryResult(False, "VALIDATED_MANUAL_DELIVERY_REQUIRED", reason="Validation passed but request constraints prohibit automated delivery")
        branch = _branch_name(self.config.branch_prefix, context.baseline.reference, context.baseline.commit)
        commands = []
        for command in (
            ["git", "reset", "--mixed", context.baseline.commit],
            ["git", "checkout", "-b", branch],
            ["git", "add", "-A", "--", *context.validation.changed_files],
            [
                "git",
                "-c",
                "user.name=Autonomous OSS Remediation",
                "-c",
                "user.email=oss-remediation@localhost",
                "commit",
                "--no-verify",
                "-m",
                "Remediate OSS vulnerabilities",
            ],
        ):
            result = self.process_runner.run_argv(
                command,
                cwd=context.workspace.repository,
                source="delivery_git",
            )
            commands.append(result.to_dict())
            if not result.succeeded:
                return DeliveryResult(False, "VALIDATED_MANUAL_DELIVERY_REQUIRED", branch=branch, reason=result.stderr, evidence={"commands": commands})
        commit_result = self.process_runner.run_argv(
            ["git", "rev-parse", "HEAD"],
            cwd=context.workspace.repository,
            source="delivery_git",
        )
        commit = commit_result.stdout.strip() if commit_result.succeeded else None
        isolated, reason = self.credential_provider.isolation_status()
        if not isolated:
            return DeliveryResult(False, "VALIDATED_MANUAL_DELIVERY_REQUIRED", branch=branch, commit=commit, reason=f"Credential isolation lost: {reason}")
        try:
            credential = self.credential_provider.resolve()
        except Exception:
            return DeliveryResult(False, "VALIDATED_MANUAL_DELIVERY_REQUIRED", branch=branch, commit=commit, reason="Credential resolution failed closed")
        push_result = self._push(context.workspace, context.baseline.remote_url, branch, credential)
        commands.append(push_result.to_dict())
        if not push_result.succeeded:
            return DeliveryResult(
                False,
                "VALIDATED_MANUAL_DELIVERY_REQUIRED",
                branch=branch,
                commit=commit,
                reason="Validated commit was created but push failed",
                evidence={"commands": commands},
            )
        repository_name = _github_repository_name(context.request.repository_url)
        title = "Remediate OSS vulnerabilities"
        body = build_pull_request_body(context)
        response = self._create_pull_request(repository_name or "", branch, context.baseline.reference, title, body, credential)
        if not response["succeeded"]:
            return DeliveryResult(
                False,
                "VALIDATED_MANUAL_DELIVERY_REQUIRED",
                branch=branch,
                commit=commit,
                reason=response["error"],
                evidence={"commands": commands, "github": response["evidence"]},
            )
        result = DeliveryResult(
            True,
            "SUCCESS",
            branch=branch,
            commit=commit,
            pull_request_url=response["url"],
            evidence={"commands": commands, "github": response["evidence"]},
        )
        self.trace.write_json("delivery/result.json", result.to_dict())
        return result

    def _push(self, workspace: RunWorkspace, remote_url: str, branch: str, credential: DeliveryCredential):
        return NonInteractiveGitAuth(workspace, self.process_runner).run(
            ["push", "--no-verify", remote_url, branch],
            cwd=workspace.repository,
            source="delivery_push",
            credential=credential,
            disable_hooks=True,
        )

    def _create_pull_request(
        self,
        repository_name: str,
        branch: str,
        base: str,
        title: str,
        body: str,
        credential: DeliveryCredential,
    ) -> dict[str, Any]:
        post = self.http_post
        if post is None:
            import requests

            post = requests.post
        url = f"{self.config.github_api_base.rstrip('/')}/repos/{repository_name}/pulls"
        try:
            response = post(
                url,
                headers={
                    "Authorization": f"Bearer {credential.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                json={"title": title, "body": body, "head": branch, "base": base, "draft": self.config.draft},
                timeout=60,
            )
            status_code = int(getattr(response, "status_code", 0))
            payload = response.json() if hasattr(response, "json") else {}
        except Exception:
            return {"succeeded": False, "error": "GitHub PR request failed", "evidence": {}}
        evidence = {
            "statusCode": status_code,
            "response": _redacted_response(payload, (credential.token,)),
        }
        if status_code not in (200, 201):
            return {"succeeded": False, "error": f"GitHub PR creation failed with HTTP {status_code}", "evidence": evidence}
        return {"succeeded": True, "url": payload.get("html_url"), "evidence": evidence}


def build_pull_request_body(context: DeliveryContext) -> str:
    findings = "\n".join(
        f"- {finding.vulnerability_id} in `{finding.coordinate}` ({finding.severity})"
        for finding in context.baseline.target_findings
    ) or "- No explicit target finding IDs were selected."
    checks = "\n".join(
        f"- {'PASS' if check.passed else 'FAIL'}: {check.name} - {check.message}"
        for check in context.validation.checks
    )
    changed = "\n".join(f"- `{path}`" for path in context.validation.changed_files) or "- No changed paths recorded."
    return (
        "## OSS Remediation\n\n"
        f"### Findings addressed\n{findings}\n\n"
        f"### Changed files\n{changed}\n\n"
        f"### Deterministic validation\n{checks}\n\n"
        f"### Agent rationale\n{context.agent_summary or 'No agent summary was provided.'}\n"
    )


def digest_changed_paths(repository: Path, changed_files: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(changed_files):
        digest.update(relative.encode("utf-8"))
        path = repository / relative
        if path.is_symlink():
            digest.update(b"<symlink>")
            digest.update(str(path.readlink()).encode("utf-8"))
        elif path.is_file():
            digest.update(f"<mode:{path.stat().st_mode & 0o777:o}>".encode("ascii"))
            digest.update(sha256_file(path).encode("ascii"))
        else:
            digest.update(b"<deleted>")
    return digest.hexdigest()


def _github_repository_name(repository_url: str) -> str | None:
    value = repository_url.strip()
    if value.startswith("git@github.com:"):
        name = value.split(":", 1)[1]
    else:
        parsed = urlparse(value)
        if parsed.hostname not in {"github.com", "www.github.com"}:
            return None
        name = parsed.path.lstrip("/")
    if name.endswith(".git"):
        name = name[:-4]
    return name if re.fullmatch(r"[^/]+/[^/]+", name) else None


def _branch_name(prefix: str, reference: str, commit: str) -> str:
    safe_reference = re.sub(r"[^A-Za-z0-9._-]+", "-", reference).strip("-") or "branch"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{safe_reference}-{commit[:7]}-{timestamp}"


def _redacted_response(payload: Any, secrets: tuple[str, ...] = ()) -> Any:
    if not isinstance(payload, dict):
        return {}
    response = {
        key: payload.get(key)
        for key in ("html_url", "number", "state", "draft", "message")
        if key in payload
    }
    for key, value in response.items():
        if not isinstance(value, str):
            continue
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        response[key] = value
    return response
