"""Offline fixtures for the shared OpenHands task foundation tests."""

from __future__ import annotations

from typing import Any


def task_request_data(
    *,
    idempotency_key: str = "repo-123-cve-batch-20261016",
    objective: str = "Resolve the identified HIGH and CRITICAL dependency vulnerabilities.",
) -> dict[str, Any]:
    return {
        "contractVersion": "1",
        "idempotencyKey": idempotency_key,
        "repository": {
            "url": "https://github.com/example/maven-app.git",
            "baseRef": "refs/heads/main",
            "expectedCommit": "a" * 40,
        },
        "objective": objective,
        "constraints": {
            "javaVersionUnchanged": True,
            "springBoot": {
                "allowPatch": True,
                "allowMinor": True,
                "allowMajor": False,
                "allowDowngrade": False,
            },
            "prohibitSuppressions": True,
            "prohibitedNewSeverities": ["CRITICAL", "HIGH"],
        },
        "acceptance": {
            "buildCommands": ["mvn clean verify"],
            "severityScope": ["CRITICAL", "HIGH"],
        },
        "agent": {
            "profile": "gate2-dependency-remediation-v1",
            "modelProfile": "vertex-gemini-2-5-flash",
            "maxIterations": 250,
            "maxValidationDenials": 3,
        },
        "intelligence": {"sbri": {"mode": "auto"}},
        "delivery": {"mode": "none"},
        "metadata": {"source": "test"},
    }
