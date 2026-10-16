# A5 execution evidence

Executed 2026-10-14 on branch
`spring-boot-release-intelligence-feasibility`, starting commit
`49929602b0e3100fdcd80025b6e3b5cae2cc0f5e`.

The accepted run contains a fresh and warm isolated A2 workload, the same fresh
and warm A5 workload, 32 graph comparisons, frozen-v2 vulnerability comparison,
storage inventories, a zero-dependency plugin bootstrap control, Maven POM/TGF
evidence, bounded logs and seven generated SVG charts.

Maven repositories were disposable directories under `/tmp` and are not
retained. No repository cache, JAR, class file or `target/` directory is part
of this evidence.

The accepted result followed two invalidated attempts documented in
`execution-attempts.json`. Cold transfer metrics are retained in
`results-a5.json`, but cold full log files were overwritten by the warm pass
before a fresh/warm filename defect was corrected. Warm logs remain. The code
now assigns pass-specific log filenames.

See `../../a5-comparison-report.md` for interpretation and
`../../live-test-cases.md` for reproduction commands.
