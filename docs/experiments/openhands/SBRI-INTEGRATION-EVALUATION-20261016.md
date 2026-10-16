# OpenHands SBRI integration evaluation — 2026-10-16

## Result

The deterministic pre-edit integration and its offline contracts passed. A
real SBRI run against the clean multi-module application completed and produced
bounded agent context without changing the source. The attempted end-to-end
OpenHands run stopped in the existing startup stage because `node` was absent,
before task worktree creation, model invocation, dependency edits or validation.
Consequently, model use of the evidence and remediation quality remain **not
observed**, not failed.

## Live pre-edit measurement

The target was the multi-module fixture at commit
`9ea1b0ed5ca255db0fc7c659d050896d3ed5db78`, with Spring Boot `4.0.6` controlled
by the parent. Candidate discovery used the timestamped live Maven Central
metadata response (SHA-256
`2d5c42a7312f688e64759aa0b6fc68253f06b96ab652156c047b4d120221160c`) and
selected the available stable forward patches `4.0.7` and `4.0.8`.

Measured results:

| Measure | Observation |
|---|---:|
| SBRI exit/status | `0` / `COMPLETE` |
| Subprocess wall time | 60.819 s |
| Integration elapsed time | 61.172 s |
| Peak process-tree RSS | 225,144 KiB |
| Full output before bounded retention | 24,917,623 bytes / 1,771 files |
| Isolated Maven cache | 21,068,345 bytes / 1,567 files |
| Downloaded dependency JARs | 50 / 14,912,596 bytes |
| Agent summary | 2,047 characters / approximately 512 tokens |
| Source changed | No |

The baseline contained 50 findings, including 26 Critical/High. Spring Boot
`4.0.7` addressed 33 original findings and left 17, including 12 Critical/High;
`4.0.8` addressed 38 and left 12, including 10 Critical/High. Neither candidate
introduced a finding in this observation. The summary exposed ownership and
selected-version changes, full evidence paths, and explicitly treated ranking
as security evidence rather than a mandatory strategy.

The bounded retained evidence is under
`evidence/sbri-integration-preedit-20261016/`. Maven repository contents,
candidate workspaces and HTTP caches were excluded; canonical results,
dependency trees, inventories and scanner responses were retained.

## End-to-end OpenHands attempt

The existing fresh-run entry point was invoked with SBRI enabled and automatic
evidence pushing disabled. It exited in `STARTUP` with:

```text
ERROR: Required command not found: node
```

The evidence is under
`evidence/gate2-task-23-orchestrated-run-20261016T024202Z/`. Authentication
preflight had succeeded, but the harness intentionally refused to proceed
without its required runtime. No model request, target branch, trajectory,
edit, build/test run or independent Stop Hook validation occurred.

## Acceptance observations

| Question | Result | Evidence |
|---|---|---|
| Is SBRI limited to applicable Spring Boot/Maven security work? | Supported offline | Applicability tests cover applicable, unrelated and non-Spring tasks. |
| Does SBRI finish before the first agent action? | Supported by ordering and direct live run | Runner calls integration before `conversation.send_message`; source fingerprints were identical before/after the live collection. |
| Is useful evidence bounded for context? | Supported | The real 24.9 MB output became a 2,047-character summary with paths to full artifacts. |
| Are partial/failure states preserved accurately? | Supported offline | Tests cover partial structured errors, failure wording and CLI exit code 2. |
| Is duplicate work avoided and recoverable? | Supported offline | Fingerprint/reuse and persistent-state recovery tests passed. |
| Did the live agent inspect SBRI before editing? | Not observed | Startup failed before model invocation. |
| Did the agent consider credible alternatives and choose from evidence? | Not observed | No trajectory exists for this attempt. |
| Did the resulting remediation build, test and pass independent validation? | Not observed | No remediation was attempted. |
| Is reasoning/remediation quality better than earlier runs? | Not established | Earlier runs did not receive equivalent SBRI evidence, and this run did not reach the model. |

## Boundaries and next evidence needed

Install the existing harness prerequisite `node`, then repeat the same fresh-run
command under the frozen task and record the trajectory plus validator output.
That run is needed to determine whether the model actually inspects SBRI,
retains autonomous strategy selection, chooses a credible remediation, and
improves or harms build/test and independent security outcomes. The present
evidence supports integration correctness and cost only; it does not justify a
claim about model reasoning effectiveness.
