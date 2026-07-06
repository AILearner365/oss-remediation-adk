# MVP-3 Follow-up TODOs

## Milestone 2 — Outcome Analysis and Planner Decision Quality

### Outcome Analysis

- Compare `baseline/baseline-build-result.json` with the current attempt validation result for build-validation failures.
- Explicitly state whether the same failure already existed before remediation.
- Explicitly state whether the patch plan introduced, worsened, or did not cause the failure.
- For Maven build failures, compare baseline build log with current attempt build log.
- If the failure is caused by a pre-existing baseline or policy constraint, state that clearly with artifact evidence.
- Confirm whether the Planning Agent had sufficient context from prior attempts and outcome-analysis summaries.
- Ensure every root-cause statement references supporting artifacts.

### Planning Agent

- The planner, not Outcome Analysis, should decide whether the next step is `PATCH_PLAN` or `MANUAL_REVIEW`.
- If Outcome Analysis shows a pre-existing baseline or project-policy blocker that cannot be safely fixed within allowed patch scope, the planner should return `MANUAL_REVIEW`.
- The planner should not keep retrying equivalent patch plans when prior outcome analysis shows the blocker is outside automated remediation scope.
- The planner should explain why manual review is required when it chooses `MANUAL_REVIEW`.

### ADK Web Retry Loop

- Keep retry execution bounded by `policy.maxAttempts`.
- Continue replanning after validation failure only when the planner returns another valid `PATCH_PLAN`.
- Stop when the planner returns `MANUAL_REVIEW`, validation succeeds, or max attempts are reached.
- Preserve attempt traceability using `replanSourceAttempt`, `replanReason`, and `replanInputOutcomeAnalysis`.

### Smoke Test Expectations

- If baseline build already fails for the same reason as validation, Outcome Analysis must say so explicitly.
- If the planner correctly identifies the issue as manual-review-only, workflow should stop with `MANUAL_REVIEW_REQUIRED` instead of burning all attempts.
- ADK Web summary should distinguish:
  - automated remediation failure,
  - pre-existing baseline failure,
  - project-policy/manual-review blocker,
  - PR delivery failure.
