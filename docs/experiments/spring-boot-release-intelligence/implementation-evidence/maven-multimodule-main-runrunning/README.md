# Maven multi-module application validation

This directory retains the 2026-10-16 standalone SBRI validation of
[`AILearner365/maven-multimodule-app`](https://github.com/AILearner365/maven-multimodule-app/tree/9ea1b0ed5ca255db0fc7c659d050896d3ed5db78)
at branch `main-runrunning`, commit
`9ea1b0ed5ca255db0fc7c659d050896d3ed5db78`.

Reproduce from the SBRI repository root after cloning that exact source commit:

```bash
./sbri evaluate \
  --project /path/to/maven-multimodule-app \
  --releases 4.0.7,4.0.8 \
  --output /tmp/sbri-maven-multimodule \
  --timeout 600
```

No Maven profile was activated. The evaluated scopes were `compile` and
`runtime`; all five severity categories were selected. See `result.json` for
the authoritative result, `report.html` for the four-table rendering,
`execution-summary.json` for provenance, `resource-measurements.json` for
resource data, and `acceptance-notes.md` for checks and limitations.

The retained `evidence/` directory deliberately excludes the isolated Maven
repository, copied source workspaces, and HTTP response cache. Every evidence
reference emitted in `result.json` resolves to a retained TGF or scanner file.
