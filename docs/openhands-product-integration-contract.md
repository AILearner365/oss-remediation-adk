# OpenHands autonomous remediation: product integration contract

Status: shared product workflow implemented; paid remediation and live GitHub delivery remain unverified. Use the [operator guide](openhands-product-operations.md) and [acceptance evidence](verification/openhands-product-20261019/report.md). This contract is not a claim of full external acceptance.

## Outcome

A user submits a Java/Maven repository and remediation goal by API, UI or CLI. The SAME backend workflow prepares the workspace, captures the baseline, optionally provides SBRI, invokes one native OpenHands coding agent with Skills and tools, runs independent Maven/OSV Stop Hook checks, reports evidence and creates an authorized draft GitHub PR for an accepted change. Agent reasoning and candidate choice remain autonomous. No prescribed Spring Boot version.

## Architectural boundaries

- **Native OpenHands SDK/Agent Server** owns the agent, tool execution, conversation identity, message/events, and Stop Hook invocation. Canvas presents native events and workspace. Do not build a second agent loop or copy all its events to a parallel custom ledger.
- **Deterministic remediation components** own Git baseline identity, Maven/OSV findings, optional SBRI evidence and candidate metadata, security acceptance/validation, and validated Git tree. A failed validation denies completion with feedback.
- **Thin product control plane** owns input authorization, idempotency, task-to-conversation correlation, durable accepted evidence and PR delivery state. Existing SQLite is transitional; retain only state that is independently authoritative, not OpenHands' native conversation content.
- **One service path** is called by API, CLI and Canvas UI integration. A metadata-only task registration API is not an execution API; do not advertise it as complete.
- **Delivery** is downstream of independent accepted validation; exact target repository, base commit, approved changed files and Git tree must match; PR push is an independently authorized effect with durable recovery on partial network failure.

## Operational contract

- Cloud Shell package caches may live in /tmp and be downloaded again on a fresh session. Durable task data, Agent Server conversations and keys must not rely solely on /tmp. Keep persistent state within the available home/durable storage quota.
- Do not treat POC smoke conversations as production tasks. Do not create them during product startup.
- Use a stable Python interpreter for Stop Hook execution; verify exact persisted hook command, timeout, task workspace and trusted source before native /run. A missing executable blocks dispatch. Never waive comparison because an expired uv build path looks familiar.
- Pinned runtime dependencies and Vertex environment must be installed once through a supported launcher. No instructions to manually assemble different uv dependency sets.
- Reopening an existing task inspects and resumes its actual state; never clone work or retry a claimed /run merely to recover an uncertain response.
- The operator should need one documented startup command and one submission mechanism. Routine restarts must not require manual task ID, Python path, or Stop Hook reconstruction.

## Evidence and acceptance

1. Original SDK/controlled OpenHands POC proves execution concepts; reuse its native Skills, tooling and deterministic validator rather than reproducing its experimental harness.
2. Real app `AILearner365/maven-multimodule-app`, `main-runrunning`, baseline commit `9ea1b0ed5ca255db0fc7c659d050896d3ed5db78`: Maven/OSV completed; 50 baseline findings; SBRI COMPLETE. Native idle conversation `883a70da-4986-4ed5-9576-006fcd84846d` linked to `task_943461f6ed864a2baf96642c61746bd0`. This conversation has **not** run Gemini; its original Stop Hook persisted an expired ephemeral Python path. Do not dispatch it until independently validated recovery/replacement.
3. The corrected stable Hook construction affects **new** conversations. It does not rewrite the old immutable native conversation.
4. Product startup, real-app API submission, Maven/OSV baseline (50 findings), SBRI COMPLETE, native idle handoff, UI evidence access and same-conversation service restart are now verified. Paid agent-produced remediation, real Stop Hook execution/feedback and actual draft PR still require separately authorized end-to-end verification. Offline tests are not proof of these external outcomes.
5. Acceptance is one automated vertical slice: fresh session startup -> API submission -> one native agent -> failure/feedback if needed -> independent PASS -> authorized draft PR -> recover/read same task through UI and API after restart, with bounded cost and evidence. Record failures as real implementation defects, not as reasons to add more orchestration layers.

## File responsibility

- `scripts/openhands_service.py`: supported start/stop/restart, pinned package reuse, persistent keys/native state, prerequisite and API/UI readiness checks. Reuses the proven published Canvas launcher functions from `openhands_native_poc.py`, without invoking its probes or smoke conversations.
- `openhands_shared/product.py`: one task lifecycle, application-stage coordination, explicit execution/delivery authorization, native observation and recovery. A small job row supplements the existing transactional store; native events stay in Agent Server.
- `openhands_shared/server.py`, `cli.py`, `ui.html`: authenticated product REST endpoints, thin HTTP CLI and minimal application submission/evidence UI. `python -m openhands_shared` now uses that CLI. Generic Canvas chat cannot express the remediation submission/approval contract; Canvas remains available for native conversation activity.
- `scripts/openhands_native_remediation.py`: native request/handoff, verified Stop Hook, one-shot dispatch.
- `openhands_shared/baseline.py`, `intelligence.py`, `validation.py`: deterministic stages.
- `openhands_shared/api.py`: legacy metadata facade retained for fixture compatibility; not the supported product server.
- `scripts/openhands_pr_delivery.py`: independent approval-gated exact-tree draft PR and durable remote reconciliation; partial push/PR failures tested with local Git and a fake GitHub transport. Live GitHub delivery remains unverified.
- The `openhands_real_*` and synthetic `openhands_native_*poc*` commands remain regression references, not operator stages. The delivery audit function and native bootstrap/handoff functions are reused directly; no experimental command chain is executed by the product.

## Do not repeat

No extra custom planner/executor, no second agent, no vulnerability recipes, no POC test mode as default startup, no stage-by-stage operator prompts, no workaround that only suppresses a safety gate, no CLI/API/UI logic drift.
