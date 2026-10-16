# OpenHands Shared Execution Flow — Architecture and Migration Agreement

Status: APPROVED DIRECTION; implementation pending.
Date: 2026-10-16
Repository: AILearner365/oss-remediation-adk
Frozen reference: openhands-gate2-frozen-20261016
Development: openhands-service-integration
Starting commit: e5d160cb6080e5c6ed8fef16ca4ba42ab6106c8f

## Objective
Evolve the proven OpenHands SDK Gate-2 experiment into a reusable, server-deployable remediation execution flow with three entry points: native OpenHands UI where integration is supported, REST API, and an experiment/test script. All three must invoke one backend lifecycle, share status/events/results, and avoid separate business logic. Use OpenHands as the agent harness, not a replacement custom agent harness.

## Non-negotiable compatibility
- Keep the existing scripts, their commands, experimental evidence collection, and current behavior unchanged until a replacement has been independently verified. Never modify the frozen reference branch or rewrite its history.
- Work exclusively on openhands-service-integration. Keep the existing openhands-poc-evaluation branch undisturbed.
- Progressively migrate deterministic stages to the shared execution flow; do not abruptly replace the experiment script.
- Do not trigger live Gemini/Vertex remediation runs without explicit authorization. Offline tests and read-only inspection are allowed.
- Do not clean or delete historical evidence/documents during the migration. First classify them.

## Shared lifecycle
1. Task configuration/contract: repository, base branch/ref, task objective, constraints, acceptance criteria, model/provider configuration, optional intelligence and delivery settings.
2. Deterministic preparation: fetch/checkout, pinned baseline commit, isolated workspace, environment/tool readiness.
3. Deterministic baseline assessment: Maven build/tests, OSV scan, original vulnerability inventory, reproducible baseline record.
4. Optional pre-agent intelligence: SBRI evidence and candidate evaluation for applicable Spring Boot/Maven tasks; skip when irrelevant. Candidate ranking does not constrain the agent's strategy or permit residual vulnerabilities.
5. OpenHands autonomous execution with available Skills/tools and independent deterministic validation/Stop Hook, with evidence-based recovery.
6. Deterministic delivery after PASS only: verify validated state unchanged, commit/push approved changes, create/reuse reviewable GitHub PR. Never auto-merge or expose delivery credentials to agent.

## Responsibilities
- Shared backend: task lifecycle, state, workspace orchestration, baseline, optional intelligence, OpenHands integration, validation, deterministic delivery, persistent events/artifacts.
- UI: task submission, progress, logs/events, results, validation and PR link. Evaluate native OpenHands capabilities before custom UI/fork.
- REST API: submit/status/events/results with idempotency and durable identifiers; use the same backend as UI.
- New experiment script (after backend parity): environment/startup checks and Cloud Shell-specific disk/memory housekeeping, API-driven trial orchestration, collection/export/comparison of agent events, traces, evidence and reports, publishing experimental artifacts for review.
- Existing experiment script: remain fully functional throughout migration.

## Vertex AI/OpenHands integration audit
Inventory actual OpenHands source/vendor patches, installed-package modifications, Vertex AI provider/model support, ADC refresh, environment loading, dependency/version pins and startup workarounds. Distinguish repository-owned adapters from upstream modifications. Verify which are supported upstream in the pinned version and newer versions; do not assume support or remove patches until behavior is proven. Record upstream contribution candidates separately. Keep credentials outside agent-visible instructions/logs.

## Implementation sequence and gates
M1 — Freeze and discovery: preserve working reference, inspect current scripts and OpenHands SDK/server/UI integration capabilities, document current state and source modifications, define shared execution boundary and migration plan. No behavioral refactor or live run.
M2 — Backend + API: introduce the minimal shared execution service, durable task identity/status/events/results, offline tests; migrate deterministic stages incrementally without duplicating logic.
M3 — UI and test-client parity: connect supported native UI path to same backend; add a thin experiment client while retaining original script; compare equivalent task contracts and output schemas across UI/API/script.
M4 — Delivery + server readiness: validation-gated GitHub PR creation, idempotent retry, isolation, persistence, deployment configuration and end-to-end authorized validation.
M5 — Documentation hygiene: designate current authoritative runbooks, classify/archive historical reports without deleting evidence, and record upstream patch resolution/contribution follow-ups.

The order of UI feasibility investigation is M1, not deferred to M3. Reorder implementation details only with documented evidence and without compromising the non-negotiable invariants.

## Acceptance criteria
- Original frozen Gate-2 script remains runnable with unchanged behavior.
- UI, API and new experiment script invoke the same backend execution lifecycle and report consistent state/events/results.
- Baseline, SBRI when applicable, OpenHands, Stop Hook and delivery are integrated without hard-coded Cloud Shell dependencies in server code.
- Independent validation PASS is required before PR delivery; retries do not duplicate commits/PRs.
- Events, tool actions, validation, artifact links and PR metadata are retrievable after worker restart.
- Vertex AI configuration/auth and any OpenHands upstream patches are explicitly inventoried and reproducible.
- No destructive cleanup of historical experiment evidence.

## Immediate next action
On openhands-service-integration, execute M1 only: read-only inventory and supported-integration feasibility; write a concise implementation plan and acceptance tests. Do not migrate code, alter frozen scripts, create PR delivery or run live experiments until reviewed.
