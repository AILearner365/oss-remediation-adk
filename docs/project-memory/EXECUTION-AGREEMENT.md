# Codex development execution agreement

**Agreed:** 2026-10-02. Applies to Codex development and verification in this repository, not to the Autonomous Agent's runtime prompts, contracts, or context.

## Choose the execution mode

| Mode | When to follow it | Responsibility |
|---|---|---|
| Cloud Shell | Current default for new implementation tasks; Codex extension initially, CLI also available | Implement, run relevant offline checks and focused live verification in Cloud Shell, inspect evidence, update project memory, and push for review. |
| Windows → Cloud Shell | When the task explicitly selects it, or development has moved back to Windows | Implement and run supported offline checks on Windows. Provide the exact Cloud Shell live commands and acceptance criteria; record live verification as pending until its evidence is inspected. |

State the selected mode once at task start. Explicit task instructions take precedence; a mode change changes where work runs, not the agent architecture or acceptance rules. Preserve both workflows and historical Windows results.

## Complete each scoped task

1. Read the existing project-memory entry points and reconcile the branch/head. Locate the actual failure and define observable acceptance criteria before editing.
2. Implement the smallest coherent fix. Add meaningful regressions for observed failures and run the relevant checks.
3. In Cloud Shell, actively use focused live verification when the change concerns model behavior, tool recovery, evidence use, workspace transitions, or execution/scanner boundaries. Inspect the trace against the acceptance criteria. Documentation-only changes do not need paid model runs.
4. If verification fails, investigate and repair within the authorized task scope and existing limits, then rerun the affected checks. Avoid repeatedly running an unchanged scenario. If an environment or scope blocker remains, report it precisely.
5. Update the appropriate existing memory documents with implementation, offline results, live observations, unresolved gaps, next action, and return point. Push code and selected review evidence to the task branch and report the commit and workspace paths concisely.

A passing run does not verify a boundary that never occurred. Label scripted/deterministic checks, autonomous live observations, failures, and **not exercised** cases separately. Synthetic malformed-call tests verify mechanics, not autonomous recovery. Keep reasoning evaluation at **CONTINUE** unless separate evidence justifies changing it.

## Keep verification proportional to Cloud Shell resources

- Check available RAM and disk before heavier work. Run builds, test suites, and live trials sequentially; avoid competing workloads.
- Begin with targeted checks and a small live exercise. Broaden or repeat only for a failure, a new change, or a remaining acceptance gap; do not impose a large full-suite or multi-trial batch on every task.
- Keep necessary journals, traces, results, diffs, and command evidence. Clean only identified disposable build/cache artifacts after needed evidence is retained; do not blanket-delete historical workspaces.
- Do not increase agent budgets, weaken isolation, or change frozen Q1–Q5 / Challenge Before Commitment to make verification pass. Do not add agents or a duplicate orchestration workflow.
- Apply this agreement through a short reference in future task prompts; do not duplicate the checklist in each prompt or expand routine memory updates into transcripts.
