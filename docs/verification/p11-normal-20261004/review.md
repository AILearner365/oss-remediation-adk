# Frozen P1.1 normal-run review — 2026-10-04

One normal CLI attempt, `run-20261004T031259Z-4d965e41`, at source `c57d21710486e49c74fd2c410440982ac1b38fd2`. Evaluation **BLOCKED** before model execution; runtime **FAILED**, capture **MISSING**, accepted reasoning **NOT EXERCISED**. This is neither an unknown-tool failure nor evidence of reasoning improvement. Raw results are unchanged; `review.json` is a separate assessment, not a replacement result or fixture score.

## Configuration and comparison

The [pre-run criteria](assessment-before-run.md) use the existing frozen experiment method. [Preflight](preflight.json) records the exact normalized request, model `gemini-2.5-flash` / Vertex, SDK versions, production hashes and comparison equality. Actual prepared target is `AILearner365/maven-multimodule-app` at `9ea1b0ed5ca255db0fc7c659d050896d3ed5db78`, branch `main-runrunning`. Request matches normal runs `021900` and `023912` exactly: 4 cycles, 80 tools, 60 LLM calls/turn, 1800-second command/turn and 7200-second overall limits, 3000-character excerpts, system Maven, pinned OSV 2.6.0, original constraints and gated auto draft delivery. No hints, injected answers, changed credentials or runtime changes.

The historical artifacts were introduced by `6b437a12`; their running checkout revision is not independently recorded here. Between that commit and this source, production-package changes are confined to `journal.py` (incoming shape/recovery support); the harness `.gitignore` also changed in `804cb584`. Reporting/replay diagnostics differ. These are material comparison limitations, alongside mutable upstream scan data and provider responses. This is not an A/B estimate against the original `e92837d4` behavior. No model reached the point of comparison in this attempt.

Cloud Shell had about 5395 MiB available RAM / 863 MiB disk before execution and 5395 MiB / 838 MiB afterward. Workloads ran sequentially. Maven 3.9.16 / Java 21.0.12.1 and scanner version evidence are adjacent files. Windows was not exercised; Windows → Cloud Shell fallback is unchanged.

## Complete trace and earliest divergence

Raw evidence directory: `autonomous-oss-remediation-workspaces/run-20261004T031259Z-4d965e41/artifacts/` (repository-root relative). All 16 `events.jsonl` records were inspected; there are no model interactions, cycle records, accepted Intent or accepted Outcome. Therefore no accepted journal/hash/candidate binding can be made. The journal contains only the preliminary contract and harness final resolution; neither is model testimony.

- Events lines 1–10: contract, scanner preflight and repository preparation; line 10 confirms target SHA.
- Line 11: `mvn clean verify` exit 0, 33.46 seconds. Complete stdout/stderr are retained under `commands/baseline_build_1-72b4518df487.*.log`.
- Line 12: scanner dependency root recorded.
- **Line 13 is the earliest observed failure:** OSV exits 128 after 0.115 seconds, visiting one directory / one inode with zero extraction calls. Line 14 classifies `NO_PACKAGE_SOURCES` as `INCOMPLETE_FATAL_FAILURE`, with no retry. The actual staged scan path is below this workspace's `temp/` directory.
- Lines 15–16: final resolution and `BASELINE FAILURE`. CLI exit 1. No model call, implementation, self-validation, independent validation or delivery occurred. Tracked authoritative diff is empty (`implementation.diff`); generated build output is excluded from retention.

`scans/baseline-attempt-1.evidence.json`, stderr, normalized report and empty raw report preserve the failure. A failed empty report does **not** mean zero vulnerabilities. `artifact-sha256.json` binds the retained raw artifacts. Baseline build success does not establish remediation or dependency suitability.

## Narrow diagnostic and separate fix proposal

Production `deterministic/osv.py:223` copies sources into `workspace.temp`, excludes `.git` through `evidence.scanner_copy_ignore`, then invokes OSV without `--no-ignore` (`osv.py:386`). The enclosing harness `.gitignore:10`, introduced by cleanup commit `804cb584`, ignores `/autonomous-oss-remediation-workspaces/*/temp/`. `git check-ignore -v` identifies that rule for the staged POM. OSV's installed help says default traversal honors `.gitignore`.

[Diagnostic source](diagnose_scan_ignore.py) and [paired output](scan-ignore-diagnostic.json) reproduce this on a fresh copy of the exact target, with production copy exclusions and a verified root POM. Both invocations disable network/transitive resolution; only the second adds `--no-ignore`. Default: exit 128, one directory, zero extraction calls. No-ignore: five POM extraction calls, 53 directories, 83 inodes; exit 127 because no offline Maven vulnerability database exists. This **demonstrates the inherited ignore/staging interaction** and restores extraction only. It is controlled infrastructure evidence, not a normal remediation retry, validation pass or natural recovery. No live model trial was repeated.

Proposed separate scope: isolate scanner staging from enclosing harness ignore rules while preserving intended target exclusions and evidence boundaries. Add a regression for staging below an ignored ancestor and for repository-local exclusions; decide the narrow mechanism after checking those semantics. Do not simply remove cache exclusion or assume globally disabling ignores is acceptable. No production fix was made in this evaluation task. The historical scanner's complete behavior under a prospective fix and a successful fresh scan remain unverified.

Reproduce the offline diagnostic from repository root while this run's untracked target clone is present:

```bash
PYTHONPATH=. python docs/verification/p11-normal-20261004/diagnose_scan_ignore.py --output /tmp/p11-scan-ignore-new.json
```

For a fresh checkout, first recreate only the target clone at the workspace `repository/` path and check out `9ea1b0ed5ca255db0fc7c659d050896d3ed5db78`; create sibling `temp/`. Install the pinned scanner at the path in `preflight.json`. The diagnostic requires a new output path and refuses an existing file. The retained pair was captured before this output-only safeguard was added; the scan operations are unchanged. It does not call the model or establish vulnerability results.

## Existing experiment per-run assessment

Evaluator: Codex, 2026-10-04. Task: documented normal request, same baseline as `021900` / `023912`.

| Existing assessment area | Observation |
|---|---|
| Q1 problem/all constraints | NOT EXERCISED; no Task to Solve/accepted Intent reached model |
| Q2 investigation, priors, uncertainty and provenance | NOT EXERCISED; no model tool/source use |
| Q3 project applicability/control/eliminations | NOT EXERCISED |
| Q4 candidates and complete coverage | NOT EXERCISED; no selected candidate |
| Q5 material challenge | NOT EXERCISED |
| Implementation and reassessment | NOT EXERCISED; empty tracked diff |
| Model self-validation / Outcome claims | NOT EXERCISED; no accepted Outcome |
| Independent validation | NOT EXERCISED; raw validation null |
| Delivery | NOT EXERCISED; NOT_DELIVERY_ELIGIBLE, no PR |

All seven predeclared reasoning criteria are NOT EXERCISED, not passes or new demonstrated reasoning failures. Existing historical Tomcat coverage, unsupported availability claims, controlled F provenance failure and G capture exhaustion remain unresolved evidence; this run does not revise them.

## Mandatory self-evaluation

- **Expected:** observe evidence-supported, complete selection and proportional Q5 challenge in a normal comparable run, followed by reassessment and truthful Outcome.
- **Observed:** successful baseline build followed by scanner staging failure before model execution.
- **Improvement:** none established.
- **Remaining failure:** normal accepted-decision gap remains; infrastructure now prevents its observation.
- **Regression:** a harness cleanup ignore rule interacts with scanner staging; paired diagnostic demonstrates extraction suppression. No reasoning regression can be assessed.
- **Search behavior:** unavailable / NOT EXERCISED; no model search exists to classify as INSUFFICIENT, PROPORTIONATE or EXCESSIVE.
- **Cost:** 34.96 seconds between first/last trace events, nine subprocess command events including a 33.46-second build; one baseline scan, zero model sessions/calls or agent tool calls, no remediation retries. No provider usage cost observed.
- **Causal interpretation:** infrastructure failure, unrelated to Q5 reasoning. Offline contrast supports ignore propagation, not a dependency/release conclusion.
- **Experiment decision:** CONTINUE; neither promotion nor refinement of frozen reasoning is warranted.
- **Evidence for decision:** full new trace, raw final result/journal, paired diagnostic and separate status review; historical failures remain documented in `docs/verification/reasoning-boundaries-20261003/investigation.md` and corrected reporting investigation.

Next action: separate scoped scanner staging/ignore repair and focused verification, then return to the same normal P1.1 evidence gap. Do not rerun this unchanged configuration merely to seek a pass.
