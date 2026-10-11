# Gate 2 Task-17 — first live test after goal-preserving guidance refinement

Status: **BOUNDED_FAIL; meaningful improvement in target coverage, but engineering acceptance not met.** Assessment 2026-10-11. Read-only review; no new guidance or runtime change.

## Experiment identity
- Evidence: [Task-17 run 20261011T044019Z](evidence/gate2-orchestrated-run-20261011T044019Z/README.md); [event trajectory](evidence/gate2-orchestrated-run-20261011T044019Z/trajectory-d155030e2c674aa29a666a6016a36680/events.jsonl), [validation](evidence/gate2-orchestrated-run-20261011T044019Z/validation.json), [attempt 1](evidence/gate2-orchestrated-run-20261011T044019Z/validation-attempt-1.json), [attempt 2](evidence/gate2-orchestrated-run-20261011T044019Z/validation-attempt-2.json), [attempt 3](evidence/gate2-orchestrated-run-20261011T044019Z/validation-attempt-3.json), [attempt 4](evidence/gate2-orchestrated-run-20261011T044019Z/validation-attempt-4.json), [final diff](evidence/gate2-orchestrated-run-20261011T044019Z/final.diff), [Git state](evidence/gate2-orchestrated-run-20261011T044019Z/git-state.txt), [metadata](evidence/gate2-orchestrated-run-20261011T044019Z/run-metadata.txt).
- Task/model/flags: `17`; `vertex_ai/gemini-2.5-flash`; `engineering_judgment_guidance=0`, `task_skill=0`, `structured_guidance=1`; `max_denials=3`, `max_iterations=250`; target baseline `9ea1b0ed5ca255db0fc7c659d050896d3ed5db78` as before.
- The **intended treatment** is only changed `general-engineering.md` guidance hash `c63431b5...`; control head `953f8453...`. Offline native AgentContext delivery preflight was reported PASS before execution. This proves delivery mechanism, not model causal use.
- Parsed full GitHub blob trajectory: **119 events** (53 ActionEvents, 53 ObservationEvents, seven MessageEvents, four Stop Hook events, one Condensation, one SystemPromptEvent). Private reasoning and omitted context cannot be inspected.

## Checkpoints and comparison

| Measurement | Task-15 | Task-16 | Task-17 |
| --- | --- | --- | --- |
| Result | PASS | BOUNDED_FAIL | **BOUNDED_FAIL** |
| Target findings provably resolved at final | 26/26 | 0/26 (all unknown) | **26/26** |
| Scannable baseline/current packages | 10/10 | 10/0 | **10/10** |
| Build/test/startup | PASS | PASS | **PASS** |
| Prohibited new findings at final | 0 | comparison unknown | **0** |
| Spring Boot policy final | PASS (4.0.8) | PASS final, interim forbidden downgrade | **PASS (4.0.8), no observed Boot 3 downgrade** |
| Completion validations | 1 | 4 | **4** |
| Event count | 128 | 273 | **119** |
| Final blocking finding | None under contract | missing scan coverage | **suppression_policy: potentially prohibited new Maven exclusions** |

The final Task-17 independent validation passed 10 of 11 checks. It did not fail vulnerability reconciliation; its `suppression_policy` check flagged added lines for `<exclusions>`/`<exclusion>` in `task-web/pom.xml`. This is a **policy violation according to current deterministic validation**, not proof that a vulnerability was intentionally concealed, and not automatically proof that all dependency exclusions are invalid engineering. The agent's own explanation was to exclude `tools.jackson.core` from `spring-boot-starter-webmvc` and manage older `com.fasterxml.jackson.core` versions instead. Compatibility, required runtime functionality and whether those exclusions are an acceptable legitimate substitution were **not** established. Until reviewed, the proposed remediation is not deliverable.

### Four validator checkpoints
- Attempt 1: **2/26** original findings resolved, 24 remain, other checks pass.
- Attempt 2: **18/26** resolved, eight remain; no forbidden Spring Boot movement.
- Attempt 3: **26/26**, coverage 10/10, no new prohibited findings, build/test/startup PASS, but `suppression_policy` **FAIL** for Maven exclusion lines and delivery hygiene **FAIL** for temporary `dependency-tree.txt`.
- Attempt 4: **26/26**, coverage 10/10, no new findings, build/test/startup PASS, delivery hygiene corrected, but the same exclusion-based suppression-policy failure persists. Fourth stop is **allowed to end experiment only**, not accepted success.

## Agent-action trace and failure attribution

1. E14/E16: directly update `commons-text` and `json`. E28 declares completion prematurely, corrected by explicit 24-remaining Stop Hook E29/E30.
2. **E22: `rm -rf ~/.m2/repository && mvn clean install`** — deleted the **entire local Maven artifact cache**, not only a named package. This is a materially disruptive agent action in a potentially shared Cloud Shell environment. The trace does not establish necessity, authorization, or impact on other tasks. Treat as a separate safety/permissions risk; do not normalize cache deletion as an engineering recovery step.
3. E35: edits parent to **4.0.9 before successful availability evidence**; E39 invokes Maven evidence Skill; E41/E42 shows parent `4.0.9` unresolvable; E43 restores 4.0.6; E47 chooses 4.0.8. Good eventual correction but weak first-version hypothesis. A future 4.0.9 retry E95/E97 again fails before E99 undo — version-availability assumption recurred.
4. E49-E61: Jackson dependencyManagement experiments include unsuccessful attempts (malformed placement, changed artifact family) and repeated builds before convergence to older `com.fasterxml.jackson.core:2.15.4` management. Patch necessity/compatibility is not proven.
5. E74/E75 Stop Hook accurately reports remaining Tomcat/Jackson vulnerabilities; E87 adds **Jackson `<exclusions>`** to Spring Boot's WebMVC starter to avoid vulnerable libraries; E101 adds `tomcat.version=11.0.25`; E109 completion claim; E110/E111 independent feedback explicitly identifies `suppression_policy` and temporary artifact.
6. **E112 removes temporary `dependency-tree.txt`; E114 views `security/dependency-check-suppressions.xml`; E116 attempts completion without modifying the XML or removing the Maven exclusions.** The agent resolved the hygiene item but not the actual blocking check. This is strong behavioral evidence of mislocalizing the policy failure as XML suppression rather than the reported `pom.xml` exclusions. The feedback summary said “Potential vulnerability suppression change detected,” but omitted the exact `task-web/pom.xml` exclusion lines visible in validation JSON. Hence **both model diagnostic failure and feedback actionability** are plausible: the validator output is clear about the category, but not precise about the offending location in the model-facing Stop Hook text. Do not blame the agent exclusively for inability to identify the file.
7. Final patch includes parent Boot 4.0.8, `tomcat.version` 11.0.25, direct Commons Text 1.15.0 and JSON 20260814, `com.fasterxml.jackson.core` management at 2.15.4, and `tools.jackson.core` starter exclusions. Those exclusions require explicit compatibility and security justification before treating the patch as a defensible fix.

## Interpretation of the guidance intervention

**Observable gains:** unlike Task-16, the agent retained scanner coverage, achieved 26/26 independently verified resolutions with no new prohibited scanner findings, never persisted a forbidden Boot 3 downgrade, and used 119 rather than 273 events. This is promising **directional evidence** consistent with the intended guidance, not proof the wording caused improvement (two variable model runs are not a controlled statistical estimate).

**Unresolved recurring issues:** early premature success claims; action before source-version verification; repeated unresolvable 4.0.9 candidate; mixed-release Jackson exclusion/substitution reasoning; failure to resolve explicit Stop Hook `suppression_policy`; and unsafe full Maven cache deletion. A model can hit all security-scan numbers while producing a non-acceptable solution.

**Harness insight:** the independent validator correctly rejected the exclusions, but the model-facing Stop Hook summary did not include exact offending exclusion file/lines from `suppression_policy.evidence.addedSuppressionLines`. The agent viewed the unrelated suppressions XML. This is a candidate **feedback fidelity gap**; verify current formatting before any code change. The current check appears conservatively to classify all added Maven exclusions as potential vulnerability suppression, including technically legitimate substitution scenarios: assess whether the rule is intentionally strict or creates false positives, without weakening the policy by default.

## Recommendation

**Do not run another identical trial or add a second generic guidance paragraph yet.** The original single intervention has useful effects but not acceptance. Before further live runs, inspect the native Stop Hook feedback builder, determine why actionable policy evidence (file and exclusion lines) was omitted, and consider the smallest deterministic *feedback presentation* correction that forwards exact violated lines without prescribing a fix. This should be isolated from any possible policy semantics change. Investigate separate tool permission/guardrails for destructive shared Maven-cache deletion; do not conflate with feedback formatting. The model retains full responsibility for deciding engineering changes, and no additional planner/critic is justified by this record.

A subsequent targeted trial should test whether the agent can identify and address the actual exclusion-based policy finding, preserve 10/10 coverage and 26/26 findings, and avoid destructive cache cleanup. If a genuinely valid exclusion-based remediation remains categorically blocked, evaluate policy design independently rather than simply telling the model to evade it.

## Follow-up implementation: feedback fidelity and shared Maven-cache permissions (2026-10-11)

### Focused feedback correction — implemented
Inspection of `scripts/openhands/openhands-gate2-stop-hook.sh` confirms that the model-facing summary already forwarded failed-check names/messages, finding identities, Spring Boot version evidence, and diagnostic artifacts but did **not** forward `suppression_policy.evidence.addedSuppressionLines` or `changedSuppressionFiles`. Task-17 attempt 3/4 validator JSON contained `task-web/pom.xml` exclusion lines. As a result the agent-facing context said only `suppression_policy: Potential vulnerability suppression change detected`; E114 inspected the unrelated suppression XML.

One narrow **presentation-only** correction now appends the exact offending file-plus-line strings (up to 24 with overflow notice) and changed suppression-file paths for a **failed** suppression check. It retains the original failure message, findings, independent policy evaluation, denial budget, and model responsibility for interpreting the evidence. It does not prescribe removal of exclusions and does not decide whether legitimate Maven exclusions should pass policy. Implemented in `scripts/openhands/openhands-gate2-stop-hook.sh`; offline regression fixture `scripts/openhands/stop-hook-feedback-preflight.py` verifies reported exclusion lines, changed suppression files, and absence on a passing check. **This preflight has been committed but not yet run in Cloud Shell.**

### Destructive Maven-cache permission review — findings, no speculative guard installed
- Task-17 exported E22 command: `rm -rf ~/.m2/repository && mvn clean install`. This is a deletion of the shared Maven artifact cache, not a narrowly scoped dependency repair. Task-16 E242 also deleted the `org/springframework/boot/` subtree. Neither event establishes necessity or proves damage to other work.
- Native agent construction uses `get_default_agent(..., cli_mode=True)`, while `configure_scanner_terminal` sets OpenHands terminal params `terminal_type="subprocess"`, shell `/bin/bash --norc`, environment overrides and scanner launcher. Conversation workspace is the task worktree; there is **no observed filesystem sandbox enforcing writes/deletes remain within the task worktree** and `~/.m2/repository` is mounted/referenced as the shared Maven registry source. Thus the agent currently has effective shell access to shared Maven cache paths under the user's credentials. The target Git worktree and validator safety do not protect against these out-of-workspace effects.
- **Recommended enforcement boundary:** use a per-run isolated Maven local repository (`-Dmaven.repo.local`/Maven settings or `MAVEN_OPTS` and scanner's registry configuration kept consistent) and, ideally, an OS/container mount/permission boundary making the host's shared `~/.m2` immutable/inaccessible to the agent. A private copy/cache seeded from trusted artifacts may reduce downloads, but must not silently affect independent validation or the version/advisory comparability experiment. Build/test, scanner launcher, Maven registry, baseline and validation need deliberate compatibility verification together.
- Do **not** rely on grep-blocking the literal `rm -rf` command, an LLM instruction alone, or rewriting arbitrary shell command text; many shell forms can delete files and agent commands need legitimate write access to their isolated workspaces. Do not indiscriminately block `mvn clean`. Do not silently alter current live execution configuration during a feedback-only experiment.

**Change boundary:** this commit family only changes Stop Hook *feedback rendering* and adds its offline regression test. The recommended terminal/cache isolation remains an **unimplemented, independently tracked safety concern**, not a claim that existing permissions were hardened. Prior to any wider/untrusted autonomous deployment, treat isolated workspace/cache and destructive-command policy as a deployment prerequisite.

**Next steps:** Run `python3 scripts/openhands/stop-hook-feedback-preflight.py` (no model) and optionally `bash -n scripts/openhands/openhands-gate2-stop-hook.sh` in Cloud Shell. Then decide whether a controlled feedback-only live comparison should precede separate cache-isolation engineering. Preserve the `0/0/1` experiment flags and identify the changed Stop Hook file hash as the single intended treatment.
