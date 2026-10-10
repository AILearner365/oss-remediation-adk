# Vertex natural-refresh acceptance evidence

- Run start: `2026-10-10T22:36:38Z`
- Run end: `2026-10-10T22:44:57Z`
- Final reviewed verdict: **INCONCLUSIVE**
- Remediation experiments launched: `0`
- Live model requests: `2`

## Exact command

```bash
OPENHANDS_SUPPRESS_BANNER=1 \
UV_CACHE_DIR=/tmp/openhands-uv-cache \
VERTEXAI_PROJECT=deutschebank-aipocs \
VERTEXAI_LOCATION=us-central1 \
uv run \
  --with 'openhands-sdk[vertex]==1.50.0' \
  --with 'openhands-tools==1.50.0' \
  python scripts/openhands/vertex-auth-natural-refresh-acceptance.py \
    --project deutschebank-aipocs \
    --location us-central1 \
    --model vertex_ai/gemini-2.5-flash \
    --timeout-seconds 5400 \
    --poll-seconds 15 \
    --report docs/experiments/openhands/evidence/vertex-auth-natural-refresh-20261010T223700Z/report.md
```

## Result

The same Python process, OpenHands `LLM`, LiteLLM Vertex handler, and cached
Compute Engine credential completed both real Gemini requests. The initial
request returned the expected marker. Google Auth's `expired` property became
true about 213 seconds before the captured token's nominal expiry; the second
request also returned its expected marker, but the token did not change, expiry
did not advance, and the credential remained invalid under Google Auth's early
refresh threshold.

The initial classifier called this FAIL because it incorrectly treated
`credentials.expired` as the token-expiration boundary. Evidence review changed
the verdict to **INCONCLUSIVE**: the original token was still before nominal
expiry and did not yet require renewal. This run therefore neither proves nor
disproves post-expiration renewal reliability.

The implementation was corrected after the run to wait until captured nominal
expiry plus a grace interval. In accordance with the one-trial constraint, the
corrected live test was not rerun. Offline regression tests prove that an early
`expired` property no longer ends the wait.

See [the structured report](report.md) for safe timestamps, versions, lifecycle
observations, and acceptance fields. No token value, credential JSON,
authorization header, principal identity, or token fingerprint is retained.
