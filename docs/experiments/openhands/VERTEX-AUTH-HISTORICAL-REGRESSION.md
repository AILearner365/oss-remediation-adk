# Vertex authentication historical regression and root-cause isolation

Investigation date: 2026-10-10. Scope: Task-06 through Task-13. No new
remediation experiment was launched, no credential mechanism was added, and no
credential material was printed or persisted.

## Executive conclusion

The confirmed failing primitive is the refresh of a Google Compute Engine
credential selected by Application Default Credentials (ADC). Cloud Shell's
metadata service-account information response lacks the `email` field required
by `google-auth`; `Credentials.refresh()` therefore raises `RefreshError` before
a Vertex request can be authenticated.

This conclusion is **PROVEN** independently at three layers in the current
session:

1. direct `google.auth.default()` returned
   `google.auth.compute_engine.credentials.Credentials`, whose explicit refresh
   failed with the Task-13 missing-email error;
2. LiteLLM 1.104.2 `VertexBase.get_access_token(None, project)` failed at the
   same Google Auth refresh;
3. OpenHands SDK 1.50.0 `LLM.completion(..., num_retries=0)` wrapped the same
   `RefreshError` as `APIConnectionError` and then
   `LLMServiceUnavailableError`.

The failure is consequently **PROVEN not to be specific to LiteLLM or
OpenHands**. It exists below both wrappers. It is **PROVEN present in the current
Cloud Shell session** and was **PROVEN present late in Task-13**. Whether it was
continuously present before Task-13, or appeared because the managed Cloud Shell
session changed, is **UNKNOWN**. Historical smoke tests prove that model calls
worked at their recorded times; they do not preserve the credential class,
expiry, metadata response, or transitive package inventory needed to distinguish
those alternatives.

Current discovery inputs further isolate the selection: `GOOGLE_APPLICATION_CREDENTIALS`
is unset, the standard local ADC JSON file is absent, and `gcloud auth list`
reports no active account. The configured gcloud project is
`deutschebank-aipocs`, but project configuration is not a credential. Under
these conditions `google.auth.default()` falls through to the Cloud Shell
metadata source. These checks disclose only presence/absence, never credential
contents or identity.

No reliable repair has been established. The current fail-closed ADC preflight
is retained as a guard, not described as a fix. Task-14 remains blocked.

## Timeline: Task-06 through Task-13

| Task | UTC run / control commit | Vertex and execution evidence | Authentication conclusion |
| --- | --- | --- | --- |
| 06 | `20261009T182315Z` / `df37d349` | Verification returned `VERTEX_OPENHANDS_VERIFY_OK`; the 27-minute OpenHands conversation reached 255 observable events, four validator cycles, and deterministic PASS. | **PROVEN:** repeated Vertex-backed agent work succeeded. No credential failure appears. Credential source and refresh occurrence are **UNKNOWN** because they were not captured. |
| 07 | `20261010T020418Z` / `4169dfe` | Verification passed; the long conversation reached 301 events and four validator invocations, ending in bounded remediation failure rather than infrastructure failure. | **PROVEN:** repeated model work succeeded. Source/refresh details remain **UNKNOWN**. |
| 08 | `20261010T032309Z` / `6d4dd1aa` | Verification passed; the conversation reached 80 agent actions and three denied stop attempts before bounded remediation failure. | **PROVEN:** model work succeeded; no auth error was captured. |
| 09 | no captured run | Commits between Task-08 and Task-10 added layered guidance and offline preflights (`3b4f8a73` through `c891e5b8`), but the evidence tree contains no Task-09 orchestrated run. | Runtime and authentication behavior are **UNKNOWN**; no run is inferred. |
| 10 | `20261010T152256Z` / `c891e5b8` | Verification passed; 33 agent actions and three validator denials occurred. A Vertex rate-limit response was captured, then execution continued to bounded remediation failure. | **PROVEN:** authenticated Vertex traffic occurred. The rate limit is not a credential failure. |
| 11 | `20261010T201012Z` / `c2c208e` | Verification passed, but deterministic baseline scanning failed before OpenHands conversation startup. | **PROVEN:** one verification call succeeded. Conversation authentication is **NOT EXERCISED**. |
| 12 | `20261010T201857Z` / `1382cf9` | Verification passed, then runner import failed on `autonomous_oss_remediation_agent` before constructing the agent conversation. | **PROVEN:** one verification call succeeded. Conversation authentication is **NOT EXERCISED**. |
| 13 | `20261010T204241Z` / `fa3de803` | Verification passed. The conversation completed three validator attempts (0/26 baseline resolved, then 2/26, 13/26, 16/26). At 20:50:47 the next call entered LiteLLM's refresh path and repeatedly failed because metadata service-account info lacked `email`. | **PROVEN:** a cached/initially usable authentication state supported earlier calls and the Compute Engine credential later failed during refresh. Exact token provenance and the instant the Cloud Shell metadata behavior changed are **UNKNOWN**. |

Task-13 remains **PARTIAL — infrastructure-interrupted**. Its original evidence
and target worktree were not modified by this investigation.

## Before/after comparison

The Cloud Shell environment and POC scripts at every recorded control commit
from Task-06 (`df37d349`) through Task-13 (`fa3de803`) have identical SHA-256
content:

| File | SHA-256 at every compared commit |
| --- | --- |
| `scripts/openhands/openhands-cloudshell-env.sh` | `148b37498bce0a07b4be28374b33b376d34506f1b35eeffbd754d37060af09cb` |
| `scripts/openhands/openhands-cloudshell-poc.sh` | `48c25957187becb73feccd557fe3c1ac399d3801aa41be72da42a92dee7b508e` |

The execution command also remained
`uv run --with "openhands-sdk[vertex]==1.50.0" --with
"openhands-tools==1.50.0"`. The runner continued to construct `LLM` with the
same model, `api_key=None`, and Vertex project/location environment variables.
There was no explicit credential file or credential JSON.

Changes between the Task-06 and Task-13 control commits affected opt-in prompt
guidance, Skill loading, scanner error handling, a session-local OSV launcher,
the Maven repository server, and runner import isolation. The only environment
mutation added to the agent terminal was scanner `PATH`/launcher configuration.
No change set `GOOGLE_APPLICATION_CREDENTIALS`, supplied Vertex credentials,
changed `api_key=None`, or modified Google Auth discovery.

Therefore:

- **PROVEN:** repository authentication initialization did not change between
  Task-06 and Task-13.
- **PROVEN:** the recent scanner/import changes did not introduce a new
  credential source or refresh algorithm.
- **LIKELY:** those changes did not cause the missing-email response. They may
  change run duration and hence the chance of reaching refresh, but duration is
  exposure, not the failing primitive.
- **UNKNOWN:** exact transitive dependency equality across runs. The SDK and
  tools were pinned, but their transitive packages were not locked and the
  historical logs do not inventory versions. Task-13 identifies LiteLLM
  1.104.2 and the current pinned resolution is LiteLLM 1.104.2 / google-auth
  2.56.3. Task-06's exact LiteLLM/google-auth versions cannot be reconstructed
  from committed evidence.

## Independent reproductions

All output below is deliberately non-secret. No token value, principal, headers,
or credential JSON was emitted.

### Direct Python Google Auth

Current host Python (`google-auth==2.56.3`):

```text
PYTHON_ADC_CLASS=google.auth.compute_engine.credentials.Credentials
PYTHON_ADC_REFRESH=FAIL
PYTHON_ADC_ERROR_TYPE=google.auth.exceptions.RefreshError
PYTHON_ADC_ERROR_MARKER=missing email
```

### Pinned LiteLLM runtime

Resolved with the production command's pins:

```text
openhands-sdk=1.50.0
openhands-tools=1.50.0
litellm=1.104.2
google-auth=2.56.3
PINNED_LITELLM_AUTH=FAIL
PINNED_LITELLM_ERROR_CHAIN=google.auth.exceptions.RefreshError
PINNED_LITELLM_ERROR_MARKER=missing email
```

### Pinned OpenHands runtime

An OpenHands `LLM` request with retries disabled failed before a model response:

```text
PINNED_OPENHANDS_AUTH=FAIL
PINNED_OPENHANDS_ERROR_CHAIN=openhands.sdk.llm.exceptions.types.LLMServiceUnavailableError -> litellm.exceptions.APIConnectionError -> google.auth.exceptions.RefreshError
PINNED_OPENHANDS_ERROR_MARKER=missing email
```

The production-like request above was an authentication probe only. It did not
create a task/worktree, invoke the remediation runner, or launch Task-14.

## Mechanism-level regression coverage

`tests/unit/test_vertex_auth_failure_mechanism.py` uses the real Compute Engine
credential class with a deterministic metadata service-account response that
contains scopes but omits `email`. It proves:

1. Google Auth rejects that exact response with `RefreshError`;
2. LiteLLM can use a cached, unexpired token and then fail through the same
   Google Auth path after that credential expires;
3. pinned OpenHands wraps the same underlying failure as
   `LLMServiceUnavailableError` without reaching Vertex.

This covers the Task-13 failure mechanism, rather than merely asserting that a
preflight function or shell invocation exists.

Results:

```text
host runtime:   2 passed, 1 skipped (OpenHands is not installed globally)
pinned runtime: 3 passed (OpenHands SDK 1.50.0 / LiteLLM 1.104.2)
```

## Existing patches and workarounds

| Item | Assessment | Reason |
| --- | --- | --- |
| Canvas launcher patch from `openhands-sdk==...` to `openhands-sdk[vertex]==...` | **Necessary for this Canvas integration; unrelated to failure** | It installs the Vertex extra. It neither chooses nor repairs credentials. |
| Canvas Vertex readiness patch | **Necessary UI compatibility workaround; unrelated to refresh** | It allows an ADC-backed Vertex model to be considered configured without an API key. It does not run Google Auth. |
| `gcloud config set project` synchronization | **Useful configuration; not authentication** | It aligns project selection only. It cannot change the Python ADC credential object or metadata response. |
| Former `gcloud auth application-default print-access-token` check | **Ineffective and misleading as a Python ADC proof; removal justified** | The gcloud CLI credential path can differ from `google.auth.default()`. A CLI token check does not prove that LiteLLM's selected credential can refresh. |
| Current Python ADC double-refresh preflight | **Necessary fail-closed guard; not a fix** | It exercises the same discovery/refresh primitive and currently blocks before worktree/state creation. Two immediate refreshes still do not prove hours-long availability. |
| Three sequential OpenHands verification requests | **Useful stronger smoke test; not a long-duration proof** | It exercises the wrapper stack repeatedly only after ADC refresh passes. It cannot establish future managed-metadata behavior. |
| LiteLLM/OpenHands automatic retries | **Ineffective for this failure and potentially noisy** | Task-13 repeated the deterministic malformed-metadata failure. Retries did not repair credentials and must not be presented as recovery. No new retry/restart mechanism was added. |
| Service-account keys, copied credential JSON, custom token refresh, forced metadata identity, or agent-visible host credentials | **Rejected / potentially harmful** | None is supported by current evidence; each would change security architecture or expose credentials. |

## Classified conclusions and blocker

| Conclusion | Classification | Support |
| --- | --- | --- |
| The immediate failure occurs in Google Auth's Compute Engine credential refresh when service-account metadata lacks `email`. | **PROVEN** | Task-13 traceback, direct reproduction, deterministic Google Auth test. |
| The failure is not specific to LiteLLM or OpenHands. | **PROVEN** | Direct Google Auth fails before either wrapper; wrapper tests preserve the cause chain. |
| No repository authentication change occurred between Task-06 and Task-13. | **PROVEN** | Authentication/bootstrap scripts and LLM credential arguments are unchanged across Task-06–13. |
| A recent transitive dependency change caused the failure. | **UNKNOWN** | Historical transitive versions were not recorded. The malformed response is provider-side input, but old-version behavior was not reconstructed. |
| The condition is Cloud Shell session/metadata dependent. | **LIKELY** | Earlier calls and smoke tests succeeded; the current session consistently returns malformed service-account info. Historical credential class and metadata payload were not captured. |
| Restarting or reauthorizing Cloud Shell will make the condition reliably disappear. | **UNKNOWN** | That transition has not been exercised, and no expiry-boundary success has been observed afterward. |
| The condition was pre-existing for the entire Task-06–13 period. | **UNKNOWN** | Successful calls do not distinguish a valid refresh from a cached token; missing historical ADC diagnostics prevent proof. |
| The existing preflight detects but does not repair long-running authentication. | **PROVEN** | It detects and blocks the condition; current refresh still fails. |
| Task-14 cannot safely proceed in the current state. | **PROVEN** | All three current reproduction layers fail; no reliable repair has been established. |

### Blocker

The managed Cloud Shell ADC source is currently not refreshable, and repository
code cannot establish why its metadata service-account response lacks `email` or
guarantee that the response remains valid for a long conversation. Changing to
a new credential architecture would be speculative and is outside the evidence.

Stop here. Reauthenticate or replace the Cloud Shell session through the
organization-supported Google Cloud workflow, then rerun the existing startup
and verification commands. Even if the two explicit refreshes and three
sequential OpenHands calls pass, long-duration reliability remains **NOT
VERIFIED** until a controlled expiry/refresh boundary or an equivalently long
observation succeeds.
