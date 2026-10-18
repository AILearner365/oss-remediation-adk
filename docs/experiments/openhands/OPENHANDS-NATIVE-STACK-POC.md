# Disposable native OpenHands Canvas/SDK integration POC

**Status: Script implemented; real Cloud Shell execution NOT YET PERFORMED.**

## Purpose

Test the smallest native connection, without the custom `openhands_shared` Task API or SQLite, while keeping the frozen Gate-2 remediation POC unchanged. This is **not** a security-validation or end-to-end remediation test.

Versions are the official *matched defaults* published in Canvas 1.27.1:

- Canvas `@openhands/agent-canvas==1.27.1` (prebuilt npm distribution)
- Agent Server, SDK, tools, workspace `1.54.0` (Canvas default)
- Automation `1.19.3` (Canvas default; launcher starts it even though this test does not use automation)

The official Canvas launcher manages one Agent Server; **do not separately launch another Agent Server** for this test. Canvas `--port` here is HTTP ingress; server and automation have separate localhost ports. SDK 1.55.1 is explicitly **out of scope** for this first matching-version test.

## One-command Cloud Shell run

Run from the integration branch, after committing/saving unrelated changes:

```bash
cd ~/oss-remediation-adk
git switch openhands-service-integration
git pull --ff-only origin openhands-service-integration
python3 scripts/openhands_native_poc.py run
```

The script checks Node 24+, npm, uvx, disk and memory; installs the published Canvas under `/tmp`; prewarms matching pinned Python distributions with `uvx`; starts the **unmodified official Canvas full-stack launcher** on localhost; then uses the native Agent Server API to create an ordinary and a remediation-tagged conversation. The remediation conversation gets one synthetic pre-agent baseline report, an effective Stop Hook command, and a context event sent with `run=false`. It verifies both conversations remain idle, their IDs, event visibility, hook configuration and Canvas's HTTP page. No user or remediation agent is run.

For Cloud Shell **Web Preview**, select port `8090` (or use supported port forwarding). The output prints native conversation URLs. **Open both in the browser** to verify rendering; a successful HTTP response alone is not browser proof. The browser is intentionally read-only for this POC: do not press Run or send prompts.

The process stays running for visual inspection. Commands:

```bash
python3 scripts/openhands_native_poc.py status
python3 scripts/openhands_native_poc.py probe    # rerun checks, reuse the same native conversation IDs
python3 scripts/openhands_native_poc.py stop
python3 scripts/openhands_native_poc.py run      # recheck persisted native conversations after a controlled restart
```

After `run` completes, the small, sanitized machine-readable result is saved at:

```text
~/openhands-native-poc-reports/native-integration-smoke.json
```

To share a result through GitHub, **explicitly opt in** by running:

```bash
python3 scripts/openhands_native_poc.py publish
```

This command verifies you are on `openhands-service-integration` with the correct origin, refuses to mix already staged files, then commits/pushes **only an allowlisted, credential-free subset** of the report under `docs/experiments/openhands/evidence/`. It does not push repository changes, workspace files, logs, model responses or environment credentials.

## Cloud Shell storage and safety

- Disposable npm global prefix, npm/uv caches, Python/uv tools, install logs, native conversations and fixture workspaces are under `/tmp/openhands-native-poc-1271`. Recreate as needed after Cloud Shell discards `/tmp`. **No broad cleanup** is performed.
- Only a small report is written under `$HOME`. This is **not** a durable production backup of native conversations; the controlled restart check works only while that `/tmp` state still exists.
- The bootstrap reuses existing matching temporary packages when present and prints heartbeat updates during long installs. If a command fails, inspect `/tmp/openhands-native-poc-1271/install.log` or `canvas.log` (do not publish raw logs; they may contain sensitive operational details).
- It binds the test ingress to localhost, uses a randomly generated test-only session key, and supplies a dummy LLM key pointing to an unavailable local endpoint. **No Vertex calls, billable model execution, real Maven/OSV/SBRI calls, PR operations, or `.git` mutations** occur on `run`.
- This test does not use or alter the frozen `scripts/openhands/*` files. It does not apply any historical Vertex patches or change the user's active `gcloud` project.
- A synthetic Stop Hook command returns DENY or ALLOW when invoked directly by the test. The synthetic evidence is removed afterward so that accidental native execution DENYs; it must **never be treated as an independent validator**.
- Full stack launcher starts Automation because that is Canvas's official default; if Cloud Shell resources prove insufficient, explicitly record this and explore a split native setup rather than silently dropping components.

## Gates and known limits

**Automated:** packages/versions, single official launcher, HTTP frontend, native conversation creation/reuse, hook attachment, native event readback, idle/no-model state, synthetic Stop Hook CLI protocol, report persistence.

**Manual:** browser visibility of normal + remediation conversations, Canvas connecting to this same server, controlled stack restart.

**Not proven in this first POC:** native `/run` executing Stop Hook, DENY-driven continuation, independent real validator, baseline failure modes, SBRI, Vertex ADC/keyless readiness, long-term cross-session persistence, real remediation, delivery, and production authorization.

These are deliberately separate follow-up gates. Do **not** mistake `NATIVE_API_SMOKE_PASSED__BROWSER_AND_NATIVE_HOOK_RUN_NOT_PROVEN` for end-to-end remediation success.

## Second compatibility pass: SDK / Agent Server 1.55.1

**Status: runner option committed; actual Cloud Shell 1.55.1 run pending.**
This compares Canvas 1.27.1 against newer Agent Server / SDK / tools /
workspace 1.55.1, using the official published Canvas launcher with
`OH_AGENT_SERVER_VERSION=1.55.1`. Canvas remains unmodified. Its bundled
1.54.0 server version stays the expected *Canvas packaging default*; the
runtime version is checked independently through native `/server_info`.

**Limited-memory Cloud Shell: stop the 1.54.0 launcher first.** Do not delete
its `/tmp` directory or conversation state. 1.55.1 gets independent ports,
credentials, conversations, npm/uv dependencies and evidence. Stop and run
a version-specific POC when switching versions:

```bash
cd ~/oss-remediation-adk
git pull --ff-only origin openhands-service-integration
python3 -m unittest discover -s tests/integration -p 'test_openhands_native_poc.py' -v
python3 scripts/openhands_native_poc.py stop
python3 scripts/openhands_native_poc.py run --server-version 1.55.1
python3 scripts/openhands_native_poc.py publish --server-version 1.55.1
```

For 1.55.1, use Cloud Shell Web Preview **port 8091**, not 8090.
No real LLM calls are made; do not press Run or configure the fake LLM.
To recheck a controlled restart on 1.55.1, use:

```bash
python3 scripts/openhands_native_poc.py stop --server-version 1.55.1
python3 scripts/openhands_native_poc.py run --server-version 1.55.1
python3 scripts/openhands_native_poc.py publish --server-version 1.55.1
```

Version-specific paths:

| Property | 1.54.0 baseline | 1.55.1 compatibility |
| --- | --- | --- |
| Web Preview port | 8090 | 8091 |
| Agent Server port | 18900 | 18910 |
| Automation port | 18901 | 18911 |
| Disposable root | `/tmp/openhands-native-poc-1271` | `/tmp/openhands-native-poc-1271-server-1551` |
| Persistent small report | `native-integration-smoke.json` | `native-integration-smoke-1.55.1.json` |

`publish --server-version 1.55.1` refuses to publish a report
for the other version. The published report includes the selected SDK /
Agent Server version, native API checks, and any failure; it contains
no credentials or raw logs. If a launch fails, inspect
`/tmp/openhands-native-poc-1271-server-1551/canvas.log` and
`install.log` locally.

This is a **compatibility smoke test**, not evidence that 1.55.1's hook
execution, Vertex ADC, browser rendering, or remediation validation
are complete. The SDK change can alter native API schemas even when
the frontend loads, so failures should be recorded before adding workarounds.

## Source-based version decisions

- Canvas 1.27.1 `config/defaults.json` pins Agent Server 1.54.0 and Automation 1.19.3, minimum compatible server 1.51.0.
- Canvas 1.27.1 `bin/agent-canvas.mjs` starts full native stack by default and offers `--frontend-only` / `--backend-only` for alternative packaging.
- OpenHands Agent Server 1.54.0 exposes native `/server_info`, `/api/conversations`, native events, and hook configuration. Creating a conversation without `initial_message` avoids auto-running the agent; adding a context event with `run=false` initializes effective hooks.
- OpenHands 1.54.0 hooks still require exit code `2` to deny. Command infrastructure errors are not independent validation PASS.

Upstream sources: `https://github.com/OpenHands/OpenHands/blob/v1.27.1/config/defaults.json`, `https://github.com/OpenHands/OpenHands/blob/v1.27.1/bin/agent-canvas.mjs`, and `https://github.com/OpenHands/software-agent-sdk/tree/v1.54.0`.
