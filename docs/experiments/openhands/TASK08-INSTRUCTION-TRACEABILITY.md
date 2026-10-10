# Task-08 instruction ownership and nine-dimensional traceability

**Status:** Task-08 candidate; no live acceptance claim. Based on pinned `openhands-sdk[vertex]==1.50.0` and `openhands-tools==1.50.0`.

## Single-source-of-truth policy

- **Native OpenHands defaults:** general autonomous engineering, tool descriptions, existing stuck detection. Do not fork or restate built-in prompts.
- **Task contract:** `docs/experiments/openhands/GATE2-TASK.md`: concrete goal, protected constraints, evidence sources, acceptance criteria. Unchanged for comparability.
- **Behavioral Skill:** `scripts/openhands/skills/evidence-driven-dependency-remediation/SKILL.md`. Only focused evidence, strategy, reassessment, continuity, and whole-goal verification guidance. No hardcoded version, fixed patch script or mandatory alternative count.
- **Legacy experimental suffix:** `scripts/openhands/guidance/engineering-judgment.md`. Preserved for historical Task-06/07 reproduction; **not combined** with Task-08 skill.
- **Independent validator:** existing native Stop Hook remains authoritative for deterministic terminal constraints and scan/build/runtime.
- **Evaluator:** `ENGINEERING-EVALUATION-SCORECARD.md` (nine dimensions, event evidence, ratings); never inject evaluator rubric wholesale into agent prompt.

## Matrix

| # | Dimension | Agent-facing owner | Independent evidence / evaluation |
|---|---|---|---|
| 1 | Guidance effectiveness | SDK explicit Skill, pinned path; legacy suffix exclusive | Static Skill presence; run log Skill path; rendered context / read or trigger **must be verified** before claiming usage; observed adherence and causal confounds |
| 2 | Evidence-driven reassessment | Skill §3 | Contradiction, revisited assumption, next strategy, independent validation feedback |
| 3 | Technical correctness | Task success and protected constraints + Skill §§4–5 | Validator result, full diff, effective dependencies, test/runtime/compatibility and missing coverage |
| 4 | Unsupported initial strategy | Skill §§1–2 | Decision-critical facts verified before consequential action; warranted alternatives and selected rationale |
| 5 | Semantic strategy fixation | Skill §3 | Repeated premise after decisive contradictory evidence versus legitimate fresh-hypothesis debugging |
| 6 | Preservation of progress | Skill §4 | Intermediate passing states, regressions, recoveries, changed scope |
| 7 | Stale/inaccurate claims | Skill §1 and §3 | Authoritative facts actually retrieved and used; distinguish bad assumptions from infrastructure |
| 8 | Solution quality | Skill §§2,4–5 | Scope, family compatibility, maintainability, upstream/downstream impact, justified change |
| 9 | Performance/efficiency | Skill §5 | Evidence yield, wasted attempts, action/time/token/cost; sufficient verification not discouraged |

## Integration specifics verified against SDK 1.50.0

- `AgentContext(skills=[...])` and `load_skills_from_dir` are present in pinned SDK.
- AgentSkills format `SKILL.md` is **advertised via available_skills** for on-demand use; with no trigger, full Skill body is **not automatically injected**. Thus **loaded and advertised ≠ read, followed or effective**. Confirm the agent actually reads Skill in first Task-08 run; if not, isolate the delivery issue before judging behavior.
- SDK `load_public_skills=False` is the pinned default. The official OpenHands `security` Skill is **not** silently assumed loaded. The public registry is independently updated, so avoid uncontrolled public-skill drift during comparable Task-08 trials.
- Skill source stays in control repo and is explicitly loaded by runner so the disposable target worktree needs no committed Skill file.
- Set `OPENHANDS_TASK_SKILL=1` for Task-08, `OPENHANDS_ENGINEERING_JUDGMENT_GUIDANCE=0`. The runner rejects enabling both; default remains historical behavior.

## Acceptance before another live comparison

1. Offline loader test proves named skill discovered and no missing/duplicate/conflicting sections; `--task-skill` is opt-in and non-combinable with suffix.
2. Record Task-08 control SHA, Skill hash, effective task contract hash, SDK/tool version, model and advisory identities.
3. During first Task-08 trial, verify advertisement and actual read/trigger behavior before attributing behavior to Skill; manual short prompt instruction to load skill would be an additional experimental variable and must be documented.
4. Score all nine dimensions with event references. Distinguish deterministic acceptance from engineering-quality acceptance. Do not compare changing advisory sets as controlled causal evidence.

**No extra LLM critic, semantic blocking mechanism, new search tool, mandatory reasoning questionnaire, or prescribed Maven solutions are part of this change.**
