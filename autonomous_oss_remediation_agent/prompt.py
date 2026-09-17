from __future__ import annotations

import json

from .config import RemediationRequest
from .models import RepositoryBaseline, ValidationReport


AGENT_INSTRUCTION = """
You are the single autonomous OSS remediation engineering agent for one prepared repository.

Investigate the repository and remediate the requested vulnerabilities directly. You may read and patch repository text and use the trusted host-native shell for repository discovery, dependency analysis, builds, tests, local Git inspection, and workspace-local helper scripts.

Requirements:
- Base decisions on repository, dependency, build, and scanner evidence.
- Respect every supplied constraint.
- Treat supplied version policies solely as remediation boundaries, not instructions to upgrade or select a particular dependency-management layer. An exact required version constrains the outcome but does not prescribe how to achieve it.
- Choose the engineering approach yourself; no patch-plan JSON is required.
- Do not use vulnerability-specific recipes from this prompt. When choosing a remediation, inspect how affected dependency versions are managed by the repository, including relevant parents, imported BOMs, properties, and existing `dependencyManagement`. Use that structure as engineering evidence, avoid redundant or unnecessary lower-level overrides, and retain discretion to use a lower-level override when repository evidence supports it. Do not treat these management layers as a required remediation order or hierarchy.
- Do not install, replace, or select OSV Scanner. Deterministic code owns scanning.
- Do not obtain credentials, push branches, or create pull requests. Deterministic delivery owns those actions.
- Treat shell cwd/path policy as operating context, not proof of hard filesystem containment.
- Inspect command failures and continue adapting within the available turn and budget.
- Do not claim success. Deterministic validation after your turn decides success.

When you have completed a useful work cycle, summarize what you changed and why. If repository evidence shows no safe remediation can satisfy the supplied constraints, respond with `NO_SAFE_REMEDIATION:` followed by the evidence-based reason.
""".strip()


def initial_message(request: RemediationRequest, baseline: RepositoryBaseline) -> str:
    payload = {
        "objective": {
            "vulnerabilityIds": list(request.vulnerability_ids),
            "severityScope": list(request.severity_scope),
        },
        "constraints": request.to_dict()["constraints"],
        "baseline": baseline.to_dict(),
        "budgets": request.to_dict()["budget"],
        "completionCriteria": [
            "required build/test/startup commands pass",
            "fresh deterministic OSV scan succeeds",
            "requested target findings are absent",
            "no new prohibited findings are introduced",
            "typed constraints remain satisfied",
        ],
    }
    return (
        "Begin the first autonomous remediation work cycle in the prepared repository. "
        "Use tools to investigate and modify it, then end the turn for deterministic validation.\n\n"
        + json.dumps(payload, indent=2, sort_keys=True)
    )


def validation_feedback(report: ValidationReport) -> str:
    return (
        "Deterministic validation failed. Continue working in the same repository and session. "
        "Use this evidence to diagnose and revise the remediation; do not merely restate it.\n\n"
        + json.dumps(report.to_dict(), indent=2, sort_keys=True)
    )
