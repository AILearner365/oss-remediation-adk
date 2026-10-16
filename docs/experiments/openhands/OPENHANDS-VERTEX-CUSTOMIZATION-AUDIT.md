# OpenHands shared execution M1 — Vertex and environment customization audit

Status: M1 audit; no workaround removed or changed. Date: 2026-10-16.

This audit follows the classification required by
[OPENHANDS-SHARED-EXECUTION-MIGRATION.md](OPENHANDS-SHARED-EXECUTION-MIGRATION.md).

## Version and configuration baseline

| Item | Current value/source | Finding |
| --- | --- | --- |
| Agent Canvas | `CANVAS_VERSION=1.24.0` in `openhands-cloudshell-poc.sh` | Exact version guarded; startup refuses a different installed version. |
| Agent Server | `OH_AGENT_SERVER_VERSION=1.50.0` | Used by Canvas launcher and ADC preflight. |
| SDK/tools | `openhands-sdk[vertex]==1.50.0`, `openhands-tools==1.50.0` in `openhands-gate2-execute.sh` | Correct direct pin for the experimental runner. A production lock must also freeze transitive dependencies. |
| Provider/model | `vertex_ai/gemini-2.5-flash` | LiteLLM model path; `LLM(..., api_key=None)` relies on ADC. |
| Vertex project/location | resolver exports `VERTEXAI_PROJECT`, `VERTEXAI_LOCATION`; defaults include a POC project and `us-central1` | Repository-owned Cloud Shell convenience, not deployable tenant configuration. |
| Google auth | SDK `vertex` extra plus Python ADC; observed package evidence includes `google-auth` and `google-cloud-aiplatform` | Upstream provider support, with repository preflight and Cloud Shell-specific reliability history. |
| Dependency environment | `uv run --with ...` | Reproducible top-level versions, but not a full lock. M1 isolated resolution showed Agent Server alone can select a different SDK. |

## Customization classification

Classification values are: (1) supported upstream without modification,
(2) repository-owned configuration/adapter, (3) required upstream patch,
(4) historical or potentially obsolete, and (5) unverified.

| Customization | Files/evidence | Class | Assessment and constraint |
| --- | --- | --- | --- |
| Vertex provider through `vertex_ai/...` | runner `LLM`, `openhands-sdk[vertex]`; successful retained runs | 1 | SDK/LiteLLM supports Vertex when the extra is installed. No SDK source modification is present in the repository. |
| ADC with `api_key=None` | runner and `verify_vertex`; Google ADC | 1 | Supported provider authentication path. Credential availability and renewal are deployment concerns. |
| Add SDK `vertex` extra to Canvas-launched server | `patch_vertex_extra` edits installed `scripts/dev-safe.mjs` from `openhands-sdk==${version}` to `openhands-sdk[vertex]==${version}` | 3 | Required for the pinned Canvas 1.24.0 local launcher to install Vertex dependencies. It is a guarded modification of installed upstream code, with `.bak`. Verify against every Canvas upgrade; contribute/fix upstream if still absent. |
| Treat `vertex_ai/` profile as configured without an API key | `patch_vertex_readiness` edits built `use-llm-configured-*.js` | 3 | Required for pinned Canvas keyless ADC readiness. It is a brittle built-bundle patch tied to one minified expression. Prefer an upstream provider-auth capability fix; never generalize by accepting every keyless model. |
| Shared project/location resolution | `openhands-cloudshell-env.sh` | 2 | Explicit environment adapter. Precedence is `VERTEXAI_PROJECT`, `GOOGLE_CLOUD_PROJECT`, active gcloud project, then POC fallback. Server config must remove the fallback and require an explicit deployment value. |
| Synchronize active gcloud project | `openhands_sync_gcloud_project` | 2 and Cloud Shell-specific | Useful for the POC; mutates user gcloud config. Do not run in server task execution. Deployments should use immutable identity/project configuration. |
| ADC double-refresh preflight | `vertex-adc-preflight.py`, `openhands_verify_vertex_adc` | 2 | Fail-closed metadata-only guard. It verifies discovery, two refreshes, project match, token validity and minimum lifetime without printing tokens. It is not custom token refresh. |
| Three sequential live SDK requests | `verify_vertex` | 2 | Stronger smoke test but live/cost-bearing and not proof of future renewal. Keep outside ordinary task submission and never run without authorization. |
| Natural refresh-boundary acceptance tool | `vertex-auth-natural-refresh-acceptance.py` and retained evidence | 2 with result class 5 | The first authorized trial was inconclusive because it did not establish post-expiration renewal. Do not claim long-run ADC reliability. |
| Cloud Shell metadata `email` failure handling | `VERTEX-AUTH-HISTORICAL-REGRESSION.md` and ADC preflight | 4/5 | Historical failure was below OpenHands/LiteLLM in Google Auth metadata. The recovered-session mechanism and long-run behavior remain unverified. Repository code detects but does not repair it. |
| `/tmp` uv cache | `DEFAULT_UV_CACHE_DIR=/tmp/openhands-uv-cache`, `prepare_runtime` | 2, Cloud Shell-specific | Protects small persistent home volume. A server image should use a normal image/build cache and writable ephemeral volume, configured by deployment. |
| Dedicated tmux directory | `~/.openhands/agent-canvas/tmux`, `TMUX_TMPDIR` | 2, Cloud Shell-specific | Avoids socket/path issues in the POC. Pinned Agent Server also manages tmux; server isolation must be validated rather than inheriting a home-directory convention. |
| Ephemeral global npm Canvas install/cache cleanup | `ensure_canvas_installed` | 2, Cloud Shell-specific | Operational bootstrap only. Production should build a pinned image; runtime package installation and patching are not acceptable deployment reproducibility. |
| Host-Python validator isolation | `openhands-gate2-validate.sh` | 2, currently required | Prevents the OpenHands ephemeral uv environment from mixing incompatible Google ADK dependencies into deterministic validation. Package validator dependencies in a dedicated worker image/process before removal. |
| Environment loading from repository `.env` | `autonomous_oss_remediation_agent/environment.py` | 2, but not used by Gate-2 scripts | CLI helper loads root `.env` with process precedence. Gate-2 shell scripts do not source `.env`; they use process/gcloud/default resolution. Shared server configuration must have one explicit loading boundary. |
| Direct `.env` files containing Google settings | ignored root and package-local `.env` observed in the workspace | 4/5 | They are not tracked and are not proof of Gate-2 runtime loading. Never depend on developer-local files in deployment or publish their contents. |
| Guidance/Skills/model flags through environment | runner `environment_flag`, execute defaults | 2 | Experiment switches, not provider patches. Shared task profiles should whitelist supported values and persist the effective profile/hash. |
| SBRI and terminal environment inheritance | `sbri_integration.py`, `configure_scanner_terminal` | 2 | Current subprocesses inherit broad host environment. A server worker must pass an allowlist and keep GitHub/delivery credentials out of the agent terminal. |

## Upstream source changes actually present

No vendored OpenHands source tree or committed patch file was found. The two
OpenHands modifications are applied at runtime to the globally installed
Agent Canvas package:

1. `scripts/dev-safe.mjs` is changed to request the SDK's `vertex` extra.
2. A built readiness JavaScript bundle is changed to accept `vertex_ai/`
   profiles without an API key.

Both modifications are guarded by exact string checks and the Canvas version
pin. They are still upstream modifications and must be treated as reproducible
patches, not repository-owned normal configuration.

## Authentication and refresh conclusions

- The repository uses standard Google ADC discovery/refresh; it does not mint,
  cache or manually refresh access tokens.
- Immediate double refresh plus sequential model requests proves current
  usability only. The retained natural-boundary test does not prove renewal
  after nominal expiry.
- A prior Cloud Shell session returned incomplete metadata and failed equally
  through direct Google Auth, LiteLLM and OpenHands. Retrying at the agent layer
  is not a repair.
- A server should use an organization-approved workload identity/service
  account mechanism with refresh behavior tested in that deployment. Do not
  copy Cloud Shell credentials or expose host credentials to agent prompts,
  tools, logs or artifacts.

## Environment boundary for the shared service

The minimal deployable boundary should be:

```text
deployment secret/identity manager
  -> worker/provider adapter (project, location, profile, ADC)
  -> native Agent Server/OpenHands LLM

task contract
  -> provider/profile reference only
  -X-> raw credentials or arbitrary environment variables
```

The worker should construct a small allowlisted agent terminal environment for
scanner/validator launchers. Delivery credentials belong to a separate
post-validation delivery process and must never be mounted into the OpenHands
workspace/runtime.

## Required follow-up evidence

1. Build a fully locked 1.50.0 server image and assert SDK/tools/LiteLLM/Google
   dependency versions at startup.
2. Test Vertex ADC and token renewal in the intended server identity, not Cloud
   Shell, with no remediation task.
3. Test unmodified current Canvas against that server. If either patch remains
   necessary, record an upstream issue/PR and retain a versioned downstream
   patch rather than editing a minified bundle at runtime.
4. Verify Canvas/Agent Server compatibility and keyless readiness before any
   version upgrade. Do not infer it from semver or current-main documentation.
5. Verify secrets are absent from native events, product events, logs and
   exported artifacts under both success and provider-error paths.
