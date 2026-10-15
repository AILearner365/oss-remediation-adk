# A7 recommendation

## Decision: CONTINUE

Do not select an A7 winner yet. S4 has the strongest result in the focused live
subset: it preserved A5 paths, avoided a second resolver, produced the same 81
scanner finding identities as S1, and generated a 21,377-byte SBOM versus
89,883 bytes. This is promising evidence, not a winner declaration.

A defensible selection still requires the full C1–C10 candidate matrix,
baseline/candidate vulnerability dispositions and severity counts, packaged
JAR/WAR comparison, independent project
scan comparison, equivalent cold/warm whole-pipeline benchmarks, peak memory,
failure injection, and cross-candidate S3 deduplication measurement.

S1–S4 therefore remain `PARTIALLY PROVEN`. Continue with the smallest next run
that exercises all four against identical baseline and multiple candidate
inputs; do not infer clean status from any partial collection or scan.
