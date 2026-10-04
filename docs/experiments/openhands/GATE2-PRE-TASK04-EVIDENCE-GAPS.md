# Gate 2 pre-Task-04 evidence hardening

## Purpose

Record the minimal evidence-quality correction required before another live OpenHands remediation run, while preserving the other Task-03 observations as evidence rather than adding new orchestration or solution guidance.

## Proven validator defect

Task-03 ended with a malformed Maven POM. The deterministic OSV run extracted six packages and then reported:

```text
Filtered 6 local/unscannable package/s from the scan.
```

The resulting OSV JSON contained no vulnerability results. The validator treated every baseline target that was absent from that incomplete observation as resolved and reported 24 resolved / 0 remaining.

That is not sufficient evidence of remediation.

## Minimal correction implemented

Target-finding comparison now fails closed when the dependency evidence is not authoritative.

The validator now distinguishes three states:

- **RESOLVED** — the target is absent and the fresh dependency evidence is comparable to the baseline.
- **REMAINING** — the target is still observed.
- **UNKNOWN / UNSCANNABLE** — the target is absent but the evidence is incomplete or coverage regressed.

For OSV source scans, the validator records baseline and current package extraction coverage from scanner output. A fresh scan cannot establish resolution when its scannable package coverage falls below the baseline. A failed build also makes the dependency comparison non-authoritative.

This is intentionally narrow. It does not prescribe dependency versions or remediation strategy.

Stop Hook feedback now includes the count of unknown/unscannable original HIGH/CRITICAL findings so the agent receives the evidence-quality failure instead of a misleading zero-remaining signal.

Focused unit coverage was added for:

- comparable OSV package coverage;
- regressed package coverage;
- failed-build evidence;
- absent target -> UNKNOWN when comparison is incomplete;
- visible target -> REMAINING even with incomplete coverage;
- absent target -> RESOLVED only when comparison is complete.

## Captured but intentionally not fixed

### Evidence-acquisition reliability

Task-03 responded to the first valid deterministic denial by trying to obtain current Spring Boot release evidence from start.spring.io and Maven Central using curl, wget, metadata retrieval, and Python. The terminal had become trapped in a pager after an earlier Git command, and those retrieval attempts did not produce usable release evidence.

Task-02 separately demonstrated that Maven Central access and Maven-native version evidence can work.

Current classification: **evidence acquisition is fragile in the observed terminal state; this does not yet prove a need for a browser/research tool.**

No new browser, research tool, Maven recipe, or hard-coded version guidance is added here.

### Convergence / recovery quality

Task-03 proved at least one sequence of deterministic denial -> same-conversation feedback -> material reassessment. Recovery quality remained poor afterward, including repeated completion claims while the build was broken.

Current classification: **feedback-driven reassessment is demonstrated; adequate convergence is not.**

No custom retry loop, planner/executor, extra Stop Hook attempts, memory layer, AGENTS.md, Skills, or prompt expansion is added here.

## Proof-of-work boundary

This change is limited to deterministic evidence interpretation and reporting. It intentionally leaves model behavior and tool-selection policy unchanged so the next live experiment can attribute differences to trustworthy validation rather than embedded remediation guidance.
