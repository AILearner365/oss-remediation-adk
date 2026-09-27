# Project continuity checkpoint

Use this when the user says **"Checkpoint project continuity."**

Review everything materially learned, decided, implemented, tested, resolved, discovered, deferred, or changed during the current conversation and reconcile it with the latest repository state.

Update the appropriate files in this folder:

- `PROJECT-DIRECTION.md` — only when overall direction, stages, backlog, status, dependencies, or sequencing materially changed.
- `WORK-STATE.md` — update the active problem/subproblem stack, why the work is active, material findings/evidence, implementation/test results, unresolved issues, immediate next action, and explicit return point.
- `DECISION-LOG.md` — add only material decisions/discoveries, including rationale/evidence, rejected or superseded approaches where relevant, and revisit conditions.

Preserve parent → child → nested problem → return-to-parent relationships. When a side problem is resolved, mark it appropriately and restore the correct parent as active.

Reconcile conversation intent with actual repository implementation and runtime/test evidence. Do not invent missing information, rewrite history merely to fit the latest conclusion, duplicate authoritative technical specifications, or update files when nothing material changed.

These are development-project continuity documents only. Never inject them into Autonomous Agent runtime prompts, Task to Solve, Cycle Intent/Outcome, orchestration, validation, configuration, or runtime model context.

Before finishing, verify that a fresh ChatGPT conversation reading the continuity files can determine:

**where the project is → what is being solved now → why → what changed → what evidence matters → what happens next → where to return afterward.**

Commit and push continuity changes to the active repository branch when repository write access is available. If write access is unavailable, report that clearly and provide the exact required changes.

Finally report concisely:

1. what continuity state changed;
2. which files were updated;
3. the resulting active problem stack;
4. the immediate next action;
5. whether the changes were pushed.
