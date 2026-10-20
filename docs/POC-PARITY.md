# Historical behavioral parity and current verification

Reference branch: openhands-poc-evaluation, pinned commit
e5d160cb6080e5c6ed8fef16ca4ba42ab6106c8f. SDK/tools 1.55.1 is the current
execution architecture, not the older POC harness. Historical restrictions are
task values, not product-wide defaults. Old branches/evidence are preserved.

## Reviewed sources and retained evidence

On that reference commit, scripts/openhands contains:
openhands-gate2-stop-hook-run.py (build_agent, guidance_delivery_evidence,
configure_scanner_terminal, Stop callback), validate-remediation, sbri_integration.py,
export-event-history.py, guidance/general-engineering.md and engineering-judgment.md,
skills/{evidence-driven-dependency-remediation,dependency-remediation-decision,
maven-dependency-evidence}/SKILL.md and project-context/AGENTS.md. The task prompt
is docs/experiments/openhands/GATE2-TASK.md.
The existing spring_boot_release_intelligence/{sbri_cli,standalone}.py establishes
the CLI evaluate/releases/range/scopes contract and raw assessment schema.
The actual runtime guidance records take precedence over stale runner flags.

Evidence directories under docs/experiments/openhands/evidence/ on the pinned branch:

| Directory / conversation | Observed result, not inferred capability |
| --- | --- |
| gate2-task-24-orchestrated-run-20261016T041326Z / f49e13db-7632-4b2f-92f3-4d613535a56e | COMPLETE/finished/PASS; one independent attempt, 26/26 original findings resolved, zero remaining, five POMs changed; 69 exported observable events; 6 terminal,26 editor,1 finish actions; 5 error observations; 3 self-validation calls |
| gate2-task-25-orchestrated-run-20261016T043317Z | ADC Python refresh startup failure; no model trajectory or validation evidence, not an engineering failure |
| gate2-task-26-orchestrated-run-20261016T043639Z / 4a4cdb19-e2eb-4ae8-98f5-8a817cb202fb | COMPLETE/finished/PASS; first attempt FAIL (16/26 resolved,10 remaining), second PASS (26/26,0 remaining),2 Stops/1 denial;44 observable events;8 terminal,8 editor,2 invoke_skill,1 finish actions;1 error observation;3 self-validation calls |
| gate2-task-26-orchestrated-run-20261016T125931Z | EXECUTE exit1: target worktree already exists; exports same conversation/prior validation. Reused artifacts, NOT another successful run |

Task 24 control commit d16bad7fef8c21c495e2bd10ca85d0b308a57a34; Task 26
0bb8e08102236fbcdae9ebc9ffc5a0b2016f3d63. Their execute.log,
run-metadata.txt, retained validation reports, final Git diff and sanitized native
trajectory/manifest supply the above facts. Both used vertex_ai/gemini-2.5-flash,
250 maximum iterations and three allowed Stop denials. Sanitized exports exclude
private reasoning/raw LLM/stats: exact token/cost totals are not established here.

Task 24 metadata flags suggest structured guidance off, while actual execute.log
GUIDANCE_DELIVERY_EVIDENCE reports decision+Maven Skills available/configured/delivered
and general/project guidance present. Task 26 also reports delivery and has two
native invoke_skill actions: actual use, not proof of causal quality improvement.
No authoritative remote version-research commands were observed in these selected
trajectories; instructions/tool availability alone do not demonstrate research.

Pre-edit SBRI was COMPLETE with source unchanged: Task 24 candidates
4.0.7/4.0.8/4.1.1, Task 26 4.0.7/4.0.8. No agent SBRI CLI call was observed in
either trajectory. Final Boot was 4.0.8, with targeted family/dependency changes;
Task 24 used Tomcat 11.0.25/Jackson 3.1.7, Task 26 11.0.27/3.2.3. These are
historical observations, NOT recommended versions or a predetermined strategy.
Earlier retained SBRI evaluation showed real intelligence; Task 23 startup
missing-node failure showed no model execution. Neither proves new product integration.

## Capability parity matrix

| Behavior / POC evidence | Current product mapping | Classification / proof boundary |
| --- | --- | --- |
| One agent investigates/edits/reassesses, Task 26 deny then PASS | Single native Conversation/Agent, terminal, task_tracker, Stop feedback | Preserved; autonomous quality of new configuration NOT live-proven |
| Latest general + decision/Maven guidance actually delivered | guidance.py native load_skills_from_dir + AgentContext; task triggers both bodies, native available_skills/invoke_skill | Restored regression; installed SDK rendering and execute_tool verified, not model compliance |
| Earlier broad evidence-driven Skill | Retained as optional alternative to decision Skill, not duplicate default | Intentional latest-guidance choice; conflicting workflow selection rejected |
| Java21/project module facts and fixed HIGH/CRITICAL/Boot constraints | Approved task project_context, structured Java/Boot/path policy/checks | Intentional generalization; no historical module/Java recipe imposed; severity filter not implemented |
| Native events, commands/errors/retries and private stats | SDK persistence/history/stats; evidence.py phase indexes + Git diff and environment | Automatic factual capture restored; fixture/real idle SDK verified; no new raw event logger |
| Agent self-validation called 3 times in each successful run | validate_remediation native tool/CLI, same validator, separate reports/budget | Restored regression; offline authority separation and SDK dispatch verified |
| Independent Stop retries/acceptance | Existing runtime.hook -> evaluate/compare -> fail feedback or complete | Preserved; controlled fixtures/native denial; new live acceptance blocked |
| Pre-edit SBRI supplied; further candidate CLI available but unused | Optional pre-edit evidence + sbri_intelligence versions/ranges/scopes, fingerprints/reuse | Adapter restored, fixtures only; existing CLI unavailable here; no live SBRI claim |
| OSV access through special historical terminal setup | Host-native terminal and installed tools, same complete-project validator | Intentional simplification, no custom launcher; network allowed but not exercised |
| Version/compatibility research guidance and tools | Native terminal + host tools/network, publication/ownership Skill methods | Configured capability, not guaranteed installed web tool or demonstrated model research |
| Git final state/validation reports/recovery evidence | Immutable exports + task/base/tree/receipt digests, bounded native resume/claims | Preserved, tested offline; new guidance/task shape is not silently applied to old saved states |
| Draft delivery proven separately by Milestone1 PR214 | Existing exact-tree/create-only/reconciliation plus explicit draft_pr policy | Safety preserved; report_only default added, no new PR/live proof |
| Mandatory cycle questionnaire in intervening product | Optional decision(strategy,rationale,observations,evidence_refs) and outcome(summary,goal_status,remaining_uncertainty,evidence_refs) | Regression corrected; no mandatory per-command record or intent-before-edit gate in normal new format |
| POC execution permissions | Current same-user host authority guard unchanged | Separate unresolved mandatory trust boundary; do not copy experimental relaxed restrictions as security guarantees |

## Guidance placement and effective loading

Stable system suffix: general-engineering plus short agent/authority rules.
Task message: approved objective/policy, original baseline findings, references,
optional pre-edit intelligence as DATA and verified project context. Domain methods:
SDK-native SKILL.md decision/Maven pair. Tool descriptions: exact purpose/authority,
not duplicate strategy. The legacy evidence-driven Skill is selectable instead of
the decision Skill; Maven evidence remains complementary. No custom manifest,
Skill loader framework or ambient user/project overrides. Packaging includes assets.

tests_native/test_sdk_parity.py uses installed 1.55.1, an inference tripwire,
actual AgentContext rendering and native execute_tool dispatch. guidance.json
records sources, selected/triggered names and rendered hashes with explicit
SDK_RENDERED_NOT_MODEL_USE. File existence alone is not the delivery proof.

## Evidence, decision records and recovery

SDK conversations/<UUID-hex> holds the complete native state/events/stats. Keep
raw private originals; sanitized historical exports are not complete originals.
Terminal/file/tool events establish actions, errors, retries and observations;
they do not reliably establish rationale, alternatives rejected or uncertainty.
At material choices/strategy changes, preserve a concise explanation in normal
native messages or cycle_evidence decision. At completion give a concise outcome
and remaining uncertainty; optional structured fields make recovery references
explicit. No reports for routine debugging/commands/edits. No hidden chain-of-thought
request or quality claim from tool counts.

Automatic preparation/pre-run/post-run snapshots record task/conversation/base,
native event location/count/manifest digest and SDK usage, current Git tree/diff,
private artifact references and safely discovered capabilities. Baseline,
preparation, self-validation, Stop attempts/feedback, SBRI requests/results and
delivery claims remain separate because events alone cannot enforce trust,
identity, exact-tree acceptance or replay safety. Absent explicit rationale/outcome
is marked absent, never synthesized; Finish still triggers independent validation.
Legacy structured intent/outcome records remain readable, with existing integrity
checks, but are not imposed on new runs. Explicit bounded recovery verifies
preparation and native persistence rather than recreating a baseline/conversation.

## Verification versus live proof

41 focused tests pass with installed SDK 1.55.1 (33 stdlib product/local/parity
checks). Actual native idle construction/restore, rendering, safe terminal and
tool dispatch/Stop denial are tested without inference; Maven/OSV/SBRI/remote
delivery outcomes use controlled fixtures. Coverage includes config precedence,
Java/Boot policy variations, report-only/PASS authorization, optional evidence,
self-check/Stop separation, SBRI candidate/cache inputs, recovery and bounds.

No Gemini, live target modification, target build/scan, push or PR was performed.
Host authority guard still blocks live preparation/build, model run, self-check,
applicable SBRI command execution, independent acceptance and delivery. Same-user
LocalWorkspace is not isolation; no configuration bypass or new infrastructure.
Other remaining deployment limits: existing SBRI CLI absent, temporary ADC setup,
local claim durability, host background process quiescence, no standalone Canvas
registration/browser proof. Historic success is not proof those limits are solved.
