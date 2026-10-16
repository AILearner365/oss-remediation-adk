# A6 evidence run

This directory contains the accepted 2026-10-14 A2/A5/A6 comparison using
independent isolated Maven repositories. `results-a6.json` is the complete
machine-readable record; `metrics-summary.json` is its review-oriented subset.

The fair timing run used quiet Maven output for all approaches. A separate
non-quiet A6 run under `telemetry-work/` supplied transfer-event and
Maven-reported-byte measurements. `a5-qualification/` and `a6-qualification/`
contain zero-dependency controls used to distinguish plugin/bootstrap JARs from
application dependency JARs.

Accepted accuracy gates were 32/32 complete-set/version comparisons, 16/16
type/classifier/scope/version record comparisons, and 64/64 vulnerability
result-set comparisons.

One A6 control attempt failed because Maven represents an empty collection with
the literal `none`. The parser was narrowly corrected, a deterministic test was
added, and the control was repeated with a new empty cache. The successful
rerun is preserved; the failure is recorded in `execution-attempts.json`.

Generated A2 reactor `target/` directories and JARs, Maven repository caches,
HTTP caches, class files, and temporary probe directories are excluded. The
hash manifest covers every committed evidence file except itself.

Reproduction commands are documented in `../../live-test-cases.md`.
