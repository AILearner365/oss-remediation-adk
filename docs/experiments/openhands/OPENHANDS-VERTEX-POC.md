# OpenHands + Vertex AI POC

## Purpose

Evaluate OpenHands as a replacement for generic coding-agent harness infrastructure in the autonomous OSS-remediation project.

The experiment intentionally keeps the product/problem layer separate from the coding-agent harness:

```text
OSS-remediation task / constraints / deterministic validation / delivery
                              |
                              v
                     OpenHands harness
                              |
                              v
                  Gemini through Vertex AI
```

The first goal is not production integration. The first goal is to determine whether native OpenHands can reliably investigate, reason, implement, observe evidence, reassess, recover, and self-validate with a thin product layer.

## Evaluation gates

1. **Reproducible setup** — preserve the exact Cloud Shell POC setup, gaps, workarounds, and rollback.
2. **Harness capability** — run a bounded real remediation task and evaluate native OpenHands behavior without importing the existing ADK orchestration.
3. **Corporate feasibility** — only if Gate 2 is promising, test package retrieval/install/executable/runtime constraints on the company laptop.
4. **Platform decision later** — if OpenHands qualifies, compare it against OpenCode using the same Gemini model, Vertex AI, repository, task, and deterministic validator before committing to a platform.

Passing Gates 1-3 makes OpenHands a qualified candidate, not an automatic winner.

## Proven working Cloud Shell stack

Observed working path on 2026-10-04:

```text
Agent Canvas 1.24.0
        |
Canvas-managed Agent Server 1.50.0
        |
openhands-sdk[vertex] 1.50.0
        |
native OpenHands agent
        |
ADC
        |
Vertex AI
        |
Gemini 2.5 Flash
```

End-to-end smoke test succeeded with:

```text
VERTEX_OPENHANDS_OK
```

No model API key was used.

## Vertex configuration

Required runtime environment:

```bash
export VERTEXAI_PROJECT="<project-id>"
export VERTEXAI_LOCATION="<region>"
```

ADC must work:

```bash
gcloud auth application-default print-access-token >/dev/null 2>&1 && echo "ADC OK"
```

The tested model identifier is:

```text
vertex_ai/gemini-2.5-flash
```

Do not hard-code company project IDs, credentials, tokens, or session API keys in this repository.

## Cloud Shell disk constraints

Cloud Shell persistent `/home` is small. During the POC it was close to full.

Useful observations:

- npm install cache can consume hundreds of MB.
- `~/.cache/uv` grew substantially when Agent Canvas launched Python environments.
- `@openhands/agent-canvas` itself occupied hundreds of MB.
- Maven cache and editor extensions are also significant consumers.

The working mitigation is to keep the OpenHands uv cache outside persistent home:

```bash
export UV_CACHE_DIR=/tmp/openhands-uv-cache
```

Useful cleanup commands when needed:

```bash
uv cache clean
pip cache purge
npm cache clean --force
df -h /home
```

Do not delete Codex, Maven, editor, or project data merely to make the POC fit unless that cleanup is explicitly intended.

## Gap 1 — Agent Canvas launcher omits the Vertex extra

### Observed

Agent Canvas 1.24.0 normally constructed the Agent Server command with:

```text
--with openhands-sdk==1.50.0
```

The backend profile validation for `vertex_ai/gemini-2.5-flash` failed with:

```text
Vertex AI partner models require the Vertex SDK.
Install with: pip install "openhands-sdk[vertex]"
```

A direct OpenHands SDK 1.50.0 smoke test using Vertex ADC succeeded.

Inspection of:

```text
@openhands/agent-canvas/scripts/dev-safe.mjs
```

showed the versioned PyPI path hard-codes the base SDK and exposes no extra-package hook.

### Temporary Cloud Shell POC workaround

For the `OH_AGENT_SERVER_VERSION` branch only, change the versioned package from:

```text
openhands-sdk==<version>
```

to:

```text
openhands-sdk[vertex]==<version>
```

The resulting running process was verified to contain:

```text
--with openhands-sdk[vertex]==1.50.0
```

### Production/GKE treatment

Do **not** plan to patch installed npm files manually in production.

The production image should install/contain the Vertex-capable OpenHands SDK/Agent Server dependency explicitly. If upstream Agent Canvas later exposes a supported Vertex-extra option, prefer it.

## Gap 2 — Canvas keyless-readiness does not recognize Vertex ADC

### Observed

The backend profile and settings were correct:

- active profile: `vertex-gemini-25-flash`
- model: `vertex_ai/gemini-2.5-flash`
- API key: null
- provider connection not broken
- backend profile validation: valid

However Canvas disabled message sending and showed that the LLM was not set up.

Inspection of the built `use-llm-configured-*.js` showed local readiness accepts either:

- a saved API key, or
- a recognized subscription/keyless configuration.

The keyless helper currently recognizes subscription authentication, with OpenAI as the subscription provider. It does not recognize Vertex ADC.

### Temporary Cloud Shell POC workaround

In the built `use-llm-configured-*.js`, extend the local keyless readiness condition so a profile whose model starts with `vertex_ai/` is considered configured.

Conceptually:

```javascript
existingKeylessCheck(profile.config) ||
profile.config?.model?.startsWith("vertex_ai/")
```

This is a frontend readiness workaround only. It does not provide credentials and does not change backend Vertex authentication.

### Production/GKE treatment

If production is headless, this Canvas-only readiness condition may be irrelevant.

If Canvas is used against the production backend, prefer an upstream-supported ADC/keyless readiness fix rather than carrying a patched minified bundle.

## Gap 3 — Canvas tmux directory was not created

### Observed

Conversation creation initially failed with:

```text
new-session: can't create socket: No such file or directory
```

System tmux worked normally.

The Agent Server environment contained:

```text
TMUX_TMPDIR=$HOME/.openhands/agent-canvas/tmux
```

but that directory did not exist.

### Cloud Shell fix

```bash
mkdir -p "$HOME/.openhands/agent-canvas/tmux"
chmod 700 "$HOME/.openhands/agent-canvas/tmux"
```

A tmux session using the exact same `TMUX_TMPDIR` then succeeded.

### Production/GKE treatment

Create/validate the required runtime directory as part of the container entrypoint or deployment setup if the same OpenHands version still requires it.

## Browser-tool warning

The Cloud Shell Agent Server reported Chromium unavailable. This was not blocking the coding POC and Chromium was intentionally not installed because of the limited disk budget.

Do not add Chromium merely to silence the warning unless a test specifically requires browser tooling.

## Reproducible local workflow

Use the script:

```bash
scripts/openhands/openhands-cloudshell-poc.sh check
scripts/openhands/openhands-cloudshell-poc.sh prepare
scripts/openhands/openhands-cloudshell-poc.sh start
```

The script is intentionally version-guarded and should stop if the installed Canvas files no longer match the known POC patterns. It must not silently patch a newer layout.

## Gate 2 — bounded capability experiment

The first real test should evaluate native OpenHands, not embed the existing ADK harness into it.

Provide only:

- the task;
- success criteria;
- constraints;
- repository/workspace;
- normal environment/tools.

Do **not** initially give OpenHands:

- custom Intent/Outcome schemas;
- the ADK recovery loop;
- the known solution;
- custom agent orchestration;
- detailed step-by-step instructions;
- prior failed strategy momentum.

Observe whether OpenHands naturally performs:

```text
investigate
-> reason
-> implement
-> observe evidence
-> reassess
-> recover/change strategy when needed
-> self-validate
```

Keep independent deterministic validation outside the agent.

Record at minimum:

- task success;
- investigation quality;
- strategy quality;
- implementation quality;
- tool usage;
- whether evidence changed reasoning;
- reassessment/recovery behavior;
- context retention;
- self-validation;
- deterministic-validation result;
- elapsed time;
- token/cost efficiency when observable;
- amount of custom configuration/prompting required.

## Workspace/branch strategy

This branch, `openhands-poc-evaluation`, is the **control/experiment branch** and retains the existing ADK project for reference and comparison.

Do not create a second full clone of this repository merely for the POC; the Cloud Shell home volume is constrained.

The actual remediation target should use its own disposable task branch/workspace. OpenHands should act on that target rather than being instructed to follow the existing ADK implementation.

## Gate 3 — corporate laptop feasibility

Run only after Gate 2 is promising.

Treat these as separate checks:

1. package/version metadata visible;
2. actual package/tarball/wheel retrieval succeeds;
3. installation succeeds;
4. installed executables/child processes are allowed to run;
5. Vertex authentication works through the company-supported mechanism.

Prior corporate experiments showed that installation success and executable permission are distinct constraints. Do not attempt to bypass endpoint security by hiding executables in alternate system/Conda locations.

## GKE target if OpenHands qualifies

Expected direction:

```text
trigger/scanner/API
      |
      v
OpenHands backend in GKE
      |
workspace + tools
      |
Gemini through Vertex AI
      |
Workload Identity / service account
      |
independent deterministic validation
      |
delivery / PR
```

Agent Canvas is optional in the production execution path and may be used only for observation/control.

Do not carry the Cloud Shell npm-file patches into production architecture by default.
