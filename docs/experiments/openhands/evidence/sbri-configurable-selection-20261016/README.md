# Configurable SBRI release-selection verification — 2026-10-16

This bounded evidence verifies the release-selection enhancement independently
of an OpenHands model run. The clean disposable application was Spring Boot
`4.0.6` at commit `9ea1b0ed5ca255db0fc7c659d050896d3ed5db78`.
The live Maven Central metadata SHA-256 was
`2d5c42a7312f688e64759aa0b6fc68253f06b96ab652156c047b4d120221160c`.

## Explicit selection

Requested `--sbri-versions "4.0.8,4.1.1"`. SBRI evaluated exactly those two
published releases plus the independently discovered baseline. All assessments
completed, the subprocess took 59.261 seconds, sampled peak process-tree RSS
was 224,880 KiB, and source/POM state remained unchanged.

## Range selection and limit

Requested `--sbri-range "4.0.x,4.1.x"`. Live metadata resolved the complete
forward stable set `4.0.7`, `4.0.8`, `4.1.0`, `4.1.1`; prereleases were
excluded. The default maximum of 12 accepted all four, all assessments
completed in 95.147 seconds, sampled peak process-tree RSS was 231,404 KiB,
and source/POM state remained unchanged.

The same request with `--sbri-max-candidates 3` was rejected before SBRI
execution with the actual count of four and guidance to narrow the range, raise
the limit, or explicitly select versions. No silent truncation or automatic
fallback occurred; see `limit-rejection/execution.json`.

Each successful directory retains `latest.json`, bounded agent summary,
canonical JSON/HTML, dependency trees, CycloneDX inventories and scanner
responses. Maven repositories, materialized candidate workspaces and HTTP
caches are excluded. These runs evaluate release-selection correctness and do
not claim that Gemini reasoning improved; no OpenHands model was invoked.
