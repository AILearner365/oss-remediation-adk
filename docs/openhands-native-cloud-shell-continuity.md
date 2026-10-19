# OpenHands native POC: Cloud Shell continuity and next live target

Status: 2026-10-19. This is a factual handoff and recovery checklist, **not** a claim that fresh-Cloud-Shell bootstrap is already automated.

## Repositories

- Control code: `AILearner365/oss-remediation-adk`, branch `openhands-service-integration`.
- **Next real Maven application test**: `https://github.com/AILearner365/maven-multimodule-app`, reference/base branch `main-runrunning`. Verified 2026-10-19 at commit `9ea1b0ed5ca255db0fc7c659d050896d3ed5db78` (re-resolve branch before any test; do not assume the SHA stays current).
- The Maven app is a Java 21, Spring Boot 4.0.6, four-module project (`task-common`, `task-domain`, `task-service`, `task-web`). It is **not** the disposable SnakeYAML fixture. Discover its actual Maven/OSV baseline and validate candidate remediations before edits.
- Never push to `main-runrunning` directly. An eventual approved delivery workflow must create a separate task-bound branch and PR targeting this reference branch. No PR has been created for the prior accepted task.

## Verified controlled SnakeYAML experiment (do not replay)

- Local-only controlled Git fixture, originally at `/tmp/openhands-real-remediation-snakeyaml-v1`, **not** a remotely hosted Maven app.
- Synthetic contract repository URL: `https://example.invalid/controlled-snakeyaml-fixture.git`; local bare remote created inside the task run root.
- Baseline commit `f44f94c2b2ec553fc3276e36e6a99a0dcc4cd13a`; `org.yaml:snakeyaml` updated from 1.33 to 2.7.
- Accepted recovery task `task_65edba181e354c6f85a000b48b879f9c`; conversation `0bd0a45c-f8b0-49e1-a502-e413b9b40a03`; accepted validated tree `3a2504263e5d15173c118b8c9bf939a280e3f698`.
- User-observed `scripts/openhands_real_workflow.py finalize`: `FINALIZED_VERIFIED_ACCEPTED`, 1/1 findings resolved, zero remaining/prohibited, native finished, durable ACCEPTED, no extra model call.
- SBRI was explicitly disabled, delivery mode `none`. The result does not prove SBRI-on or GitHub PR delivery.
- Do **not** invoke one-shot dispatchers again for these previously claimed identities.

## Code and runtime pins

- Canvas 1.27.1 / native Agent Server 1.55.1, native agent tools and SDK 1.55.1.
- Vertex model `vertex_ai/gemini-2.5-flash`; LiteLLM 1.105.1.
- Project `deutschebank-aipocs`, region `us-central1`; native Agent Server must actually inherit `VERTEXAI_PROJECT`, `VERTEXAI_LOCATION`, and `GOOGLE_CLOUD_PROJECT`, not merely the invoking shell.
- `scripts/openhands_native_poc.py` implements version-pinned native stack setup, ports and private session key handling. For 1.55.1 defaults are Canvas 8091 and backend 18910.
- `scripts/openhands_real_workflow.py` provides `prepare-idle`, `monitor-finalize`, `finalize`, `preserve`. None authorizes or initiates Gemini. `prepare-idle` is one-shot and has **not** been end-to-end exercised on a fresh session.
- The older explicit dispatcher scripts contain immutable *historical* task IDs. They are not generic dispatch for a new repo. Billable dispatch requires a new explicitly approved, task-bound one-shot mechanism.
- Current `TaskRequest.from_dict` restricts delivery to `mode=none`; PR delivery is not implemented within the current shared task contract. Treat older ADK documents mentioning PR tools as design references, not evidence of deployed native delivery.

## Surviving vs ephemeral state

Committed in GitHub: source, scripts, offline tests and this handoff. Latest reported offline suites: 31 OpenHands real integration tests and 17 shared validation tests PASS (Cloud Shell). These counts cover the specified suites, not the entire repository.

Cloud Shell local and **not** automatically restorable from Git: `/tmp/openhands-real-durable-task-recovered-v1/state/tasks.sqlite3`, `/tmp/openhands-real-durable-task-recovered-v1/stop-hook.json`, task workspace/artifacts, native stack under `/tmp/openhands-native-poc-1271-server-1551`, OSV scanner installation, running server and authentication state.

User verified archive under home:
`~/openhands-native-poc-reports/accepted-evidence-task_65edba181e354c6f85a000b48b879f9c/`
with `shareable/manifest.json` and `private/tasks.sqlite3` plus `private/working-tree.patch`. Private files may hold sensitive content. This is evidence preservation, **not** a tested complete runtime restoration. Cloud Shell home persistence itself depends on the Cloud Shell environment and account lifecycle.

## Safe fresh-session checks (no model run)

```bash
git clone --branch openhands-service-integration https://github.com/AILearner365/oss-remediation-adk.git ~/oss-remediation-adk
cd ~/oss-remediation-adk
python3 -m unittest discover -s tests/integration -p 'test_openhands_real_*.py' -q
python3 -m unittest discover -s tests/integration -p 'test_openhands_shared_validation.py' -q
python3 scripts/openhands_native_poc.py --help
test -f ~/openhands-native-poc-reports/accepted-evidence-task_65edba181e354c6f85a000b48b879f9c/shareable/manifest.json
```
If clone path exists, **do not** overwrite it; inspect `git status` and `git branch --show-current` first and use `git pull --ff-only` only when safe. Tests require their Python dependencies installed and therefore may fail on a new shell until prerequisites are restored.

Check runtime paths and prerequisites rather than assuming they persisted:
```bash
command -v python3; command -v node; command -v npm; command -v uvx
command -v mvn; command -v java; command -v osv-scanner
test -f /tmp/openhands-real-durable-task-recovered-v1/state/tasks.sqlite3
test -f /tmp/openhands-real-durable-task-recovered-v1/stop-hook.json
```

## Required work before claiming cloud-shell-refresh reproducibility

1. Implement and test an idempotent, bounded `doctor` / bootstrap/restore workflow for pinned native services, Java/Maven/scanner dependencies, and credentials **without printing or embedding secrets**.
2. Separate installation/state restoration from **task dispatch**. Never silently trigger billable inference, rerun claimed executions, rewrite archived records, or reuse stale native conversation IDs.
3. Verify archive checksums and restore into a new unique location if recovery is needed; reconciliation must preserve evidence provenance. Until tested, do **not** assume archive implies successful recovery.
4. Enable approved repository-targeted task preparation for `main-runrunning` with current commit verification, deterministic baseline and SBRI if applicable. Avoid hard-coded fixture-specific assumptions.
5. Add durable, idempotent Git branch/commit/push/PR delivery after verified acceptance with source/target allowlist, task identity and validated-tree preconditions. Do not create a PR until a new task is legitimately validated and authorized for delivery.
6. Prove fresh-session readiness with a clean-room **offline** test before authorizing any further Vertex inference.

## Operating rule

Successful existing fixture acceptance remains valid even if `/tmp` vanishes. Missing temporary state is not proof that the previous accepted remediation failed. A new real application scenario requires its own baseline, evidence, explicit paid-run approval and delivery authorization.

## New setup and delivery commands (2026-10-19)

Read-only readiness report (safe on fresh Cloud Shell):

```bash
cd ~/oss-remediation-adk
python3 scripts/openhands_cloud_shell_setup.py
```

Explicitly install/start the pinned 1.55.1 smoke stack (may download packages, creates *idle smoke* conversations but **does not execute Gemini**, and does not restore task state):

```bash
python3 scripts/openhands_cloud_shell_setup.py --start-native
```

Delivery preview for a **newly accepted task actually bound to** `https://github.com/AILearner365/maven-multimodule-app`, `refs/heads/main-runrunning` and its exact current commit:

```bash
python3 scripts/openhands_pr_delivery.py --task-id task_<NEW_TASK_ID> \\
  --hook-config /path/to/new/stop-hook.json \\
  --expected-base <40-HEX-GIT-SHA>
```

Default is no-push. An authorized later invocation may supply `--approve-delivery I_AUTHORIZE_PUSH_AND_PR` and `GITHUB_TOKEN` for GitHub API access; the Git push also requires locally available Git credentials. **Do not** use the old SnakeYAML task: its contract URL is a placeholder and delivery mode was `none`. Never publish private evidence attachments.

Implementation scope caveat: the delivery utility is initially standalone, not yet a durable transactional delivery stage in the shared task store. It is therefore **not certified for unattended use**. Failure after branch push requires manual inspection, not blind retry. The repo-targeted real-app baseline/setup path and a clean-environment recovery drill remain to be implemented and verified. Existing generic delivery mode contract is still `none` and must not be bypassed. No live push or PR has been tested.

Offline checks:

```bash
python3 -m unittest discover -s tests/integration -p 'test_openhands_pr_delivery.py' -q
python3 -m unittest discover -s tests/integration -p 'test_openhands_real_*.py' -q
python3 -m unittest discover -s tests/integration -p 'test_openhands_shared_validation.py' -q
```
