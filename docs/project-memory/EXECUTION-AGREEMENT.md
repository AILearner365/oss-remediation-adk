# Codex development execution agreement

**Agreed:** 2026-10-02. **Updated:** 2026-10-03. Applies to Codex development and verification in this repository, not to the Autonomous Agent's runtime prompts, contracts, or context.

## Choose the execution mode

| Mode | When to follow it | Responsibility |
|---|---|---|
| Cloud Shell | Current default for new implementation tasks; Codex extension initially, CLI also available | Implement, run relevant offline checks and focused live verification in Cloud Shell, inspect evidence, update project memory, and push for review. |
| Windows → Cloud Shell | When the task explicitly selects it, or development has moved back to Windows | Implement and run supported offline checks on Windows. Provide the exact Cloud Shell live commands and acceptance criteria; record live verification as pending until its evidence is inspected. |

State the selected mode once at task start. Explicit task instructions take precedence; a mode change changes where work runs, not the agent architecture or acceptance rules. Preserve both workflows and historical Windows results.

## Complete each scoped task

1. Read the existing project-memory entry points and reconcile the branch/head. Locate the actual failure and define observable acceptance criteria before editing.
2. Implement the smallest coherent fix. Add meaningful regressions for observed failures and run the relevant checks.
3. For model/runtime behavior or capability-boundary changes, inspect existing test scenarios and reuse a suitable one; add or extend a reusable live scenario only when needed for meaningful coverage. Use existing runners, fixtures and [scenario documentation](../harness-design-review/RETAINED-EVIDENCE-ACCEPTANCE.md). Writing the scenario, running it, and retaining its results are separate responsibilities: a `results.txt` file or a generic run that never exercises the changed behavior does not satisfy scenario coverage. In Cloud Shell, run focused live verification and inspect the trace against its acceptance criteria. Apply this proportionally: documentation-only changes and deterministic reporting fixes do not automatically require a new scenario or paid live test.
4. If verification fails, investigate and repair within the authorized task scope and existing limits, then rerun the affected checks. Avoid repeatedly running an unchanged scenario. If an environment or scope blocker remains, report it precisely.
5. Update the appropriate existing memory documents with implementation, offline results, live observations, unresolved gaps, next action, and return point. Push code and selected review evidence to the task branch and report the commit and workspace paths concisely.

Each reusable live scenario records the behavior/boundary tested, required setup and exact runnable command, observable acceptance criteria and automated checks where practical, evidence/artifact locations, and explicit **passed**, **failed**, **blocked**, and **not exercised** outcomes. State whether it tests controlled integration or autonomous model behavior.

A deliberately injected malformed call can verify controlled live integration, but is not naturally occurring autonomous recovery. A successful run that never encounters the relevant boundary must report that boundary as **not exercised**. Keep scenario coverage, execution status and retained results distinct; keep reasoning evaluation at **CONTINUE** unless separate evidence justifies changing it.

## Keep verification proportional to Cloud Shell resources

- Check available RAM and disk before heavier work. Run builds, test suites, and live trials sequentially; avoid competing workloads.
- Begin with targeted checks and a small live exercise. Broaden or repeat only for a failure, a new change, or a remaining acceptance gap; do not impose a large full-suite or multi-trial batch on every task.
- Keep necessary journals, traces, results, diffs, and command evidence. Clean only identified disposable build/cache artifacts after needed evidence is retained; do not blanket-delete historical workspaces.
- Do not increase agent budgets, weaken isolation, or change frozen Q1–Q5 / Challenge Before Commitment to make verification pass. Do not add agents or a duplicate orchestration workflow.
- Apply this agreement through a short reference in future task prompts; do not duplicate the checklist in each prompt or expand routine memory updates into transcripts.
