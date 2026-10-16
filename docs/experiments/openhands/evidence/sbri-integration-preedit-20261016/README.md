# SBRI pre-edit integration evidence — 2026-10-16

This bounded bundle retains a successful invocation of the OpenHands pre-edit
SBRI integration against the clean multi-module fixture at commit
`9ea1b0ed5ca255db0fc7c659d050896d3ed5db78`.

The integration discovered Spring Boot `4.0.7` and `4.0.8` from Maven Central
metadata for the `4.0.6` baseline. `latest.json` records the exact request,
input hashes, command, measurements and source-before/source-after state.
`agent-summary.txt` is the bounded text prepared for agent context, while
`output/result.json`, `output/report.html`, dependency trees, CycloneDX
inventories and scanner responses retain independently inspectable evidence.

The source remained unchanged. The run completed with exit code 0 in 60.819
seconds of measured subprocess wall time and reached 225,144 KiB sampled peak
process-tree RSS. It produced 24,917,623 bytes in 1,771 files before retention;
21,068,345 bytes were the isolated Maven cache and are deliberately excluded
from this review bundle. The retained evidence is approximately 2.3 MiB.

This proves the integration can create and bound real pre-edit evidence. It
does not prove that an OpenHands model read or used the evidence; the full live
workflow attempt was blocked during startup before the model ran.
