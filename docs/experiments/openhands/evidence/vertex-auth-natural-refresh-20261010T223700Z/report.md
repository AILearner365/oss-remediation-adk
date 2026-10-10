# OpenHands Vertex natural credential refresh acceptance

- Started: `2026-10-10T22:36:38.713934+00:00`
- Completed: `2026-10-10T22:44:57.343688+00:00`
- Verdict: **INCONCLUSIVE**
- Model: `vertex_ai/gemini-2.5-flash`
- Project: `deutschebank-aipocs`
- Location: `us-central1`

## Dependency versions

- `openhands-sdk==1.50.0`
- `openhands-tools==1.50.0`
- `litellm==1.104.2`
- `google-auth==2.56.3`

## Scenario and acceptance criteria

One Python process creates one OpenHands `LLM`, completes a real Vertex request,
observes the exact credential cached by LiteLLM, waits without model calls until
that credential naturally reports `expired`, then completes a second request through
the same `LLM`. PASS requires same-handler and same-credential identity, a changed
in-memory token value (value never recorded), advanced expiry, valid post-boundary
credentials, and both expected model responses.

## Post-run evidence review

The initial implementation treated `credentials.expired == true` as the natural
expiration boundary. The live evidence disproved that assumption: Google Auth
reported `expired` at `22:44:56Z`, while the captured token's nominal expiry was
still `22:48:29Z` (about 213 seconds later). The second request succeeded, but
the same token and effectively the same expiry remained afterward. Therefore
the original token had not yet required renewal, natural renewal was not
established, and the generated `FAIL` verdict was corrected to
**INCONCLUSIVE**. No second live trial was launched. The implementation now
waits past nominal token expiry plus a grace interval.

## Safe authentication observations

- `boundaryCrossed`: `true`
- `boundaryCrossedAt`: `"2026-10-10T22:44:56.167099+00:00"`
- `boundaryPollCount`: `34`
- `discoveredCredentialClass`: `"google.auth.compute_engine.credentials.Credentials"`
- `discoveredCredentialSource`: `"metadata-server"`
- `discoveredProjectMatches`: `true`
- `discoveredTokenPresent`: `false`
- `discoveredValid`: `false`
- `discoveryAndRequestCredentialSameObject`: `false`
- `expiredPropertyAtBoundary`: `true`
- `expiryAdvanced`: `false`
- `expiryAdvancedSeconds`: `0`
- `initialCredentialExpiryUtc`: `"2026-10-10T22:48:29.548881+00:00"`
- `initialCredentialLifetimeSeconds`: `708`
- `initialCredentialValid`: `true`
- `initialRefreshSucceeded`: `true`
- `initialRequestCompletedAt`: `"2026-10-10T22:36:41.148594+00:00"`
- `initialRequestStartedAt`: `"2026-10-10T22:36:38.921852+00:00"`
- `initialRequestSucceeded`: `true`
- `initialTokenPresent`: `true`
- `naturalRenewalEstablished`: `false`
- `postBoundaryCredentialExpiryUtc`: `"2026-10-10T22:48:29.218475+00:00"`
- `postBoundaryCredentialValid`: `false`
- `postBoundaryRequestCompletedAt`: `"2026-10-10T22:44:57.341148+00:00"`
- `postBoundaryRequestStartedAt`: `"2026-10-10T22:44:56.172587+00:00"`
- `postBoundaryRequestSucceeded`: `true`
- `postBoundaryTokenPresent`: `true`
- `requestCredentialClass`: `"google.auth.compute_engine.credentials.Credentials"`
- `requestCredentialSource`: `"metadata-server"`
- `sameCredentialObject`: `true`
- `sameLiteLlmHandler`: `true`
- `sameLlmClient`: `true`
- `tokenChanged`: `false`

## Events

- `2026-10-10T22:36:38.881439+00:00` **ADC_DISCOVERED** — `{}`
- `2026-10-10T22:36:41.148694+00:00` **INITIAL_MODEL_REQUEST_SUCCEEDED** — `{}`
- `2026-10-10T22:36:41.149713+00:00` **WAITING_FOR_NATURAL_BOUNDARY** — `{"credentialExpired": false, "secondsUntilNominalExpiry": 708, "timeoutRemainingSeconds": 5399}`
- `2026-10-10T22:41:41.155333+00:00` **WAITING_FOR_NATURAL_BOUNDARY** — `{"credentialExpired": false, "secondsUntilNominalExpiry": 408, "timeoutRemainingSeconds": 5099}`
- `2026-10-10T22:44:56.163722+00:00` **WAITING_FOR_NATURAL_BOUNDARY** — `{"credentialExpired": true, "secondsUntilNominalExpiry": 213, "timeoutRemainingSeconds": 4904}`
- `2026-10-10T22:44:56.167163+00:00` **NATURAL_REFRESH_BOUNDARY_CROSSED** — `{}`
- `2026-10-10T22:44:57.341198+00:00` **POST_BOUNDARY_MODEL_REQUEST_COMPLETED** — `{}`

## Limitations

- This is one natural refresh-boundary observation, not a guarantee for every future Cloud Shell session.
- The test observes LiteLLM 1.104.2 internals pinned by OpenHands SDK 1.50.0; cache structure changes must fail closed.
- Offline simulations validate instrumentation only and never count as live reliability evidence.
