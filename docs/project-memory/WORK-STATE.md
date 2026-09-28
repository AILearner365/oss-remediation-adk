# Autonomous Agent — Work State

**Updated:** 2026-09-27. **Repository:** `AILearner365/oss-remediation-adk`, branch `context-hygiene-clone-challenge-before-commitment`. This is a development conversation bookmark, not an agent runtime checkpoint. Read [PROJECT-DIRECTION](PROJECT-DIRECTION.md) for the stages and IDs.

## Active stack and return point

1. **Main objective:** reliable, general autonomous problem solving, first evaluated on OSS remediation.
2. **S3 / P1:** engineering decision quality varies; a valid remediation can still reflect premature elimination of a better project-native control point.
3. **P1.1:** evaluate the frozen Challenge Before Commitment behavior at Q5 using the [experiment record](../EXPERIMENT_1_CHALLENGE_BEFORE_COMMITMENT.md), baseline `e92837d`.
4. **P1.1a — completed:** durable project continuity under `docs/project-memory/`.
5. **P1.1b / P2 — evidence audit sufficiently complete:** the six recent runs were reconciled across pre-Intent reasoning/tool use, authoritative implementation, scanner/runtime behavior, deterministic validation, and Intent retry evidence. The audit localized specific harness/runtime/capture defects and separated them from genuine reasoning variance.

**Current return point:** do **not** change Q1–Q5 or the frozen Challenge Before Commitment wording yet. P2.1 and P2.3 are implemented and locally verified; P2.2 has deterministic handoff coverage. Next obtain a clean targeted model-backed runtime-resource trace, then return to repeated P1.1 evaluation.

**Harness cleanup checkpoint (2026-09-27):** The current branch separates text replacement from explicit whole-file deletion and gives rejected Intent submissions targeted structural repair guidance. A P2.3 follow-up removed the four-identical-error early stop: error labels do not prove lack of progress, and the existing ten-turn/ten-submission checkpoint limits bound recovery. The existing current-cycle runtime-resource resolver was retained; a command-created resource was handed to an experimental scanner consumer in an integration-style unit test. A clean model-backed experiment → build/resource → experimental scan → Intent trace is still required before broad P1.1 reruns. The sections below preserve the audit's original return sequence and historical findings.

## Immediate next sequence

### Step 2 — make destructive editing unambiguous (implemented)
The latest bad run deleted the entire root `pom.xml` because `edit_workspace_text(action="delete")` maps to file unlinking while the model used it as if it meant delete text. The model-facing contract does not clearly say that `delete` deletes the whole file.

Preferred direction:
- keep text edits on explicit `write` / `replace`;
- use `replace(old_text, "")` for text removal;
- make whole-file deletion a clearly named destructive capability such as `delete_workspace_file`, or otherwise remove the ambiguous action.

Treat this as a harness/tool-contract fix, not a reasoning-prompt fix.

Implemented: `edit_workspace_text` accepts write/replace only, including empty-string replacement for text removal. `delete_workspace_file` names whole-file deletion and follows the same phase/workspace routing.

### Step 3 — prove experimental Maven → scanner runtime-resource handoff (model acceptance pending)
Current code supports `scan_current_repository(runtime_resource_path=...)`, and each cycle tells the model its experimental HOME/TEMP/logical `/tmp` plus that acquired resources should be passed to capabilities that need them.

What remains unproven is a clean model-backed path:

```text
experimental edit
→ Maven build/resource creation
→ scan_current_repository(workspace="experiment", runtime_resource_path=...)
→ successful experimental scan
→ Intent
```

This is acceptance evidence for the existing P2 runtime-resource design, not a new architecture.

Current verification: a command-created current-cycle runtime directory reaches an experimental scanner consumer outside repository source state. Existing resolver tests cover missing, foreign-cycle and out-of-bound paths. The exact model-backed Maven → scanner → Intent trace remains unproven.

### Step 4 — reduce Intent capture/schema retry friction (implemented)
Rejected Intent submissions in the recent runs were primarily structural capture errors, especially:
- required material-assumptions subsection missing;
- candidate heading/required field missing;
- COMPLETE/PARTIAL classification missing.

The repeated retries did not represent useful additional engineering search. Investigate the smallest harness/schema recovery improvement that helps the model correct the same structural failure efficiently without adding domain reasoning or changing Q1–Q5.

Implemented: rejected submissions expose focused structural repair instructions; retry prompts use the same instructions. The follow-up removed the identical-error stop and relies on the existing checkpoint turn and submission limits. Orchestration stops immediately when submissions are exhausted within one turn. Valid and substantive Intent rules are unchanged.

### Step 5 — freeze and rerun comparable benchmark runs
After Steps 2–4 are implemented/verified, run the same benchmark repeatedly from equivalent starting conditions. Keep task success separate from engineering decision quality.

Compare:
```text
Q2 investigation/evidence
→ Q3 ownership/control points and solution space
→ Q4 evidence-supported candidates
→ Q5 Challenge Before Commitment
→ selected solution
→ implementation/reassessment
→ deterministic validation
```

### Step 6 — decide Experiment 1 from clean evidence
Use the experiment protocol:
- `PROMOTE` only if repeated clean runs show materially more consistent project-fit selection with proportionate cost;
- `REFINE` if a narrow evidence-backed adjustment is needed;
- `ADVANCE` if same-model challenge helps but remains insufficient;
- `REJECT` if it adds cost/text without useful improvement;
- otherwise `CONTINUE` for more clean evidence.

Current decision remains **CONTINUE**. Do not promote, refine, advance, or reject based on the contaminated recent final outcomes alone.

## Evidence audit conclusions

### What the six recent runs established
- None of the six demonstrated a **successful experimental vulnerability scan before Intent**.
- `010345` attempted the experimental scanner twice, but both failed with `RUNTIME_RESOURCE_UNAVAILABLE` after Maven succeeded using `-Dmaven.repo.local=/tmp/.m2_repo`. It later succeeded on an authoritative scan.
- The other five committed without a successful pre-Intent scanner result.
- Therefore recent runs do **not** establish that compact scanner responses caused reasoning degradation, and they do **not** behaviorally prove pre-Intent scanner compaction/retrieval behavior.
- Successful runs used different investigation depths; scanner-before-Intent was not uniformly present even when final task success was achieved.

### Genuine reasoning evidence remains
Multiple runs still let unsupported or stale prior expectations materially influence selection:
- `203027` / `204425` treated Spring Boot `4.0.6` as non-standard/custom and eliminated the parent path too early.
- `013334` effectively reinterpreted `4.0.6` as a hypothetical/erroneous 3.x value and selected `3.2.5`.
- `015136` similarly treated `4.0.6` as invalid/custom and selected a 3.x parent.
- `011309`, on the same project class, instead treated `4.0.6 → 4.0.7` as an allowed patch move and found the higher-level parent control point, then reassessed from scanner evidence during implementation.

This keeps #18 / #22 / #25 active: stale-prior substitution, insufficient investigation before commitment, and inconsistent project-native control-point synthesis.

### Same-cycle reassessment remains a strength
`011309` showed the desired behavior:
```text
initial parent-level strategy
→ authoritative scan leaves Tomcat findings
→ parent version revised
→ explicit Tomcat override added
→ clean scan
```
Do not constrain this mechanism.

### Destructive edit failure is classified
The root `pom.xml` disappearance in `015136` is explained by tool semantics, not mysterious state corruption:
`edit_workspace_text(action="delete", path="pom.xml")` unlinked the whole file. The model-facing description was not explicit enough about that destructive meaning. Final BLOCKED/FAILED outcome is therefore contaminated by a harness/tool-contract defect and cannot be treated as pure strategy-quality evidence.

### Intent retry failures are classified
Repeated rejected `submit_cycle_intent` responses were mostly schema/format enforcement, not repeated engineering reconsideration. They should be counted as capture/overhead evidence, not as useful search depth.

## Repository state and boundaries

The branch contains `autonomous_oss_remediation_agent`, journal designs and Experiment 1. `prompt.py` / `journal.py` contain Q5 Challenge Before Commitment and the no-forced-candidate-count rule. `toolset.py` contains bounded scanner responses, retained-evidence retrieval, explicit experimental workspace selection, and optional scanner `runtime_resource_path`. `orchestrator.py` injects current experimental HOME/TEMP/logical `/tmp` into each cycle message.

Stable boundaries:
- one candidate remains valid when evidence genuinely eliminates alternatives;
- do not force candidate counts;
- do not add Maven/Spring-specific solution recipes;
- failed retrieval preserves uncertainty;
- deterministic validation stays authoritative within the validity of its observed environment/state;
- bounded + recoverable evidence remains the intended architecture;
- do not infer a prompt defect from a harness/runtime/capture defect;
- do not change Q1–Q5 while Steps 2–4 are being cleaned up.

## Open questions after the audit

- Can the model successfully exercise current-cycle Maven runtime-resource handoff into an experimental scanner?
- What is the smallest safe tool-contract change that removes ambiguous whole-file deletion?
- What is the smallest capture/recovery change that avoids repeated identical Intent schema retries?
- After those are clean, does Q5 actually reduce stale-prior elimination/premature convergence across repeated comparable runs?
- Does N+1 correctly distinguish strategy failure from harness/environment/validation failure?
- The separately discussed `autonomous-problem-solving-operating-model.md` is still not located on this branch; reconcile it before relying on exact wording.

After targeted model-backed runtime-resource acceptance, make Step 5 the active focus. After clean repeated runs, return directly to P1.1 Experiment 1 disposition.
