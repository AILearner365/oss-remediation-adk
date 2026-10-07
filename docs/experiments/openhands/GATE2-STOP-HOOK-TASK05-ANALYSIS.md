# Gate 2 Task-05: evidence-based Stop Hook review

Review date: 2026-10-07. **BOUNDED_FAIL; CONTINUE EVALUATION.**

## 1. Executive conclusion

Task-05 proves useful initial remediation, working native completion control, improved deterministic evidence transport, and inadequate sustained engineering reassessment by the tested Gemini 2.5 Flash agent. It does not prove a missing OpenHands capability or missing tool caused the failure.

The first independent check confirmed two of 25 original targets resolved, a passing build and complete scan, no new prohibited findings, and passing Java/Boot policies. Immediately after that feedback, **E27 changed the Spring Boot parent from 4.0.6 to 3.2.5 while retaining `spring-boot-starter-webmvc`**. This forbidden downgrade is the first material post-feedback divergence. E30 immediately reported missing dependency-version management; E60 subsequently reported the explicitly versioned artifact absent. The much later 2.7.18 downgrade is a culmination, not the origin.

Attempts 2–4 all failed build, scan and Java/Boot configuration policies. Each classified all 25 targets as UNKNOWN, not resolved. There was meaningful temporary recovery between attempts 3 and 4: Boot 4.0.6 restoration produced two successful builds and usable SBOM scans. The agent then returned to Boot 3.2.5 and finally 2.7.18. Thus “no recovery at the acceptance boundaries” is accurate; “no successful action after attempt 1” is not.

The dominant observed problem is model/agent evidence interpretation and engineering judgment: forbidden platform changes, confusion about artifact families and Jackson coordinates, repeated local edits despite contradictory results, and unsupported environmental attribution. Hidden knowledge deficiencies and condensation-caused context loss remain unproven. Native stuck detection was enabled but did not interrupt this varied sequence; that is not proof OpenHands lacks stuck detection.

Recommendation: stop repeating the same-model OpenHands experiment without a new hypothesis. Proceed to the already planned OpenCode comparison under equivalent contract, independent validation, bounds and model-availability constraints. A stronger-model isolation experiment remains useful if an approved model becomes available; current availability was not re-probed here. No Task-06 or remediation was run. The final change relative to the remote branch is documentation only; its existing metadata fix is retained.

## 2. Proven deterministic outcome

The [baseline](evidence/gate2-orchestrated-run-20261006T002206Z/baseline.json) records target commit `9ea1b0ed5ca255db0fc7c659d050896d3ed5db78`, successful `mvn clean verify`, OSV 2.6.0 with Maven-aware local-repository support, and 25 HIGH/CRITICAL finding identities. These are captured scanner assertions, not a fresh review-time advisory audit.

| Boundary | Build/tests | Scan | Resolved / remaining / unknown | New prohibited comparison | Java configuration | Boot policy | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [Attempt 1](evidence/gate2-orchestrated-run-20261006T002206Z/validation-attempt-1.json), E23 | PASS | Completed with findings | 2 / 23 / 0; complete | PASS; 0 | PASS | PASS; 4.0.6 | DENY |
| [Attempt 2](evidence/gate2-orchestrated-run-20261006T002206Z/validation-attempt-2.json), E193 | FAIL | Incomplete fatal failure | 0 / 0 / 25; incomplete | Unavailable; check FAIL | FAIL | FAIL; 3.2.5 + added property | DENY |
| [Attempt 3](evidence/gate2-orchestrated-run-20261006T002206Z/validation-attempt-3.json), E245 | FAIL | Incomplete fatal failure | 0 / 0 / 25; incomplete | Unavailable; check FAIL | FAIL | FAIL; 3.2.5 + added property | DENY |
| [Attempt 4 / final](evidence/gate2-orchestrated-run-20261006T002206Z/validation-attempt-4.json), E406 | FAIL | Incomplete fatal failure | 0 / 0 / 25; incomplete | Unavailable; check FAIL | FAIL | FAIL; 2.7.18 + added property | ALLOW termination only |

The initial resolved identities are `CVE-2022-42889|org.apache.commons:commons-text` and `CVE-2023-5072|org.json:json`. The remaining 23 findings cover Spring expression 7.0.7 (1), Spring MVC 7.0.7 (3), Micrometer core 1.16.5 (2), Tomcat embed core 11.0.21 (9), Jackson core 3.1.2 (3), and Jackson databind 3.1.2 (5). The latter two use group `tools.jackson.core`.

Attempt-1 coverage counters are 16 extracted / 6 filtered / 10 scannable, matching baseline. Attempts 2/3 report 6 / 0 / 6; attempt 4 reports 6 / 6 / 0. These are extraction counters, not exhaustive resolved-dependency counts. The incomplete scan and failed build independently prevent trustworthy target comparison. Empty remaining/new arrays in attempts 2–4 do **not** prove security success or absence of introduced vulnerabilities.

All four reports pass ancestry, Git evidence, suppression and the existing filename-based hygiene check. `deliveryEligible=true` is a narrow eligibility field, not acceptance; every report has `passed=false`. The hygiene heuristic misses the downloaded `.pom` artifact (section 10).

**Java qualification:** baseline protects the exact configuration set `java.version=21`, `maven.compiler.release=21`. E161 adds `maven.compiler.source=21` and `maven.compiler.target=21`; these persist. The evaluator compares configuration tuples when no single protected numeric version is specified. Its FAIL is real under the existing policy, but **a numeric Java-version change or JDK downgrade is not evidenced**. Do not equate the label with a move away from Java 21.

[Execution log](evidence/gate2-orchestrated-run-20261006T002206Z/execute.log) records `FINAL_STATUS=finished`, four hooks, three denials, `DETERMINISTIC_VALIDATION_PASSED=False`, and `GATE2_STOP_HOOK_RESULT=BOUNDED_FAIL`. [Status](evidence/gate2-orchestrated-run-20261006T002206Z/status.txt) records stage EXECUTE and exit 2. Conversation termination is not deterministic acceptance.

## 3. Evidence and provenance

Primary bundle: [Task-05 evidence](evidence/gate2-orchestrated-run-20261006T002206Z/README.md). Main behavioral source: [407-event observable stream](evidence/gate2-orchestrated-run-20261006T002206Z/trajectory-d39c00c206a94097a1139edffb1059be/events.jsonl), with [manifest](evidence/gate2-orchestrated-run-20261006T002206Z/trajectory-d39c00c206a94097a1139edffb1059be/manifest.json). **E numbers are the stored zero-based `sequence` values, not JSONL line numbers.** E0–E406 are contiguous: 193 actions, 193 paired observations, eight messages, four hooks, eight condensations and one system prompt. Each action is followed by its matching `tool_call_id` observation.

Run identity: Task 05; conversation `d39c00c206a94097a1139edffb1059be`; target branch `openhands-poc-task-05-stop-hook`; model `vertex_ai/gemini-2.5-flash`; SDK/tools 1.50.0; control commit `4c2ec4821c1f24f2c38ff61fe6a80d8bfb08399b`; three allowed denials and maximum 250 iterations. The local review checkout began at `ab40b5f6` (the evidence-capture commit); remote HEAD was `85b05b05a8199bf8ec251e593f68c319b63c4295`. The initial push exposed that the checkout lacked five existing remote Task-05 review commits. Those commits were fetched and merged without rewriting history; their findings were reconciled and duplicate handoff entries consolidated. The remote metadata fix `c67b6e2ece41fee650a93a035ef3337a0d3e80a9` is retained unchanged. Pre-existing dirty nested workspaces in the control repo were left alone.

**Observed** below means captured messages, actions, arguments, results, hook feedback, deterministic reports or Git state. Agent statements are evidence of claims, not proof of their factual content. **Inference** means a conclusion drawn from these observations. **External research** is separated in sections 7/13. No hidden chain-of-thought was inspected or reconstructed. Manifest verification reads raw source bytes for hashes, not reasoning payloads. Condensation payloads are omitted by the observable exporter.

Inspected controls: [task contract](GATE2-TASK.md), [Stop Hook experiment](GATE2-STOP-HOOK-EXPERIMENT.md), [runbook](GATE2-ORCHESTRATED-RUNBOOK.md), [runner](../../../scripts/openhands/openhands-gate2-stop-hook-run.py), [hook](../../../scripts/openhands/openhands-gate2-stop-hook.sh), [validator isolation wrapper](../../../scripts/openhands/openhands-gate2-validate.sh), [baseline](../../../scripts/openhands/openhands-gate2-baseline.py), [validation entry point](../../../scripts/openhands/openhands-gate2-validate.py), [constraint evaluator](../../../autonomous_oss_remediation_agent/deterministic/constraints.py), [deterministic validator](../../../autonomous_oss_remediation_agent/deterministic/validation.py), and [exporter](../../../scripts/openhands/export-event-history.py). The runner, hook, baseline/validation entry points, exporter and fresh-run script were unchanged between the recorded run commit and initial local review checkout. Remote commit `c67b6e2e` subsequently fixed fresh-run metadata; the other listed controls remain unchanged. E1 confirms the actual supplied contract; historical task-01 labels in control prose do not override that event or the actual branch metadata.

The inspected [OSV implementation](../../../autonomous_oss_remediation_agent/deterministic/osv.py) serves local Maven repository roots over a loopback registry and includes `--data-source`/`--maven-registry` in deterministic scan commands. It classifies extraction/resolution errors as incomplete even when JSON exists. Captured baseline/validator commands exercise this support; the agent's initial bare recursive scans do not. This explains why using the same scanner executable is not evidence of equivalent scan completeness. The later SBOM route demonstrates a working agent-owned alternative without changing independent acceptance.

## 4. Chronological observable trajectory

| Events | Observed work and result |
| --- | --- |
| E1–11 | Receives explicit no-Java-change/no-Boot-downgrade constraints; lists repo, invokes OSV at E4, reads JSON at E6, and reads root POM after repairing a relative-path editor error. E5 reports unresolved local `task-domain`/`task-common` snapshot dependencies. E7 contains the two direct dependency advisories. This is partial security evidence, not a complete target inventory. |
| E12–23 | Updates commons-text 1.9→1.10.0 and JSON 20230227→20231013. E14/15 `mvn clean install` succeeds. E16/17 OSV still fails local-module resolution, exit **127**. E18/19 reads empty `results`; E20 removes its two JSON output files. E22 nevertheless claims all criteria met. E23 (00:29:02) independently establishes valid partial progress and rejects completion. |
| E24–38 | Full finding feedback arrives as a user-role environment message. E25 rereads root POM; E27 downgrades parent 4.0.6→3.2.5. E29/30 downloads legitimate Boot parent/BOM artifacts, then fails because `spring-boot-starter-webmvc` has no managed version. E31 reads web POM. E33 removes both previously upgraded direct dependencies; E35/36 still fails. |
| E39–80 | Adds/removes unversioned management entries (E39/43/47/65), widening missing-version errors to other starters/Spring context. Pins Spring context 6.1.6 and Boot starters 3.2.5 (E51/57; E53 replacement fails). E59/60 reaches web artifact resolution and reports nonexistent `webmvc:3.2.5`. E61/63 remove versions; E69 introduces version properties; E71 manages explicit dependencies. E73/74 sees cached absence; E75 forces update; E77 deletes cached webmvc and Boot BOM directories; E79 still fails. No successful artifact-family verification precedes these edits. |
| E81–126 | `curl -o spring-boot-starter-webmvc-3.2.5.pom` writes 554 bytes, returns exit 0. No observed body inspection or XML validation follows. First condensation is E83. Parent/BOM/plugin-management permutations follow: E84 fails to match; E88 removes parent; E90/92 edit management; E96 pins plugin; E100 restores parent; E102 removes BOM; E108 shifts plugin configuration. E112/114 use property versions, E118/120 return to explicit versions. Missing version/artifact persists. E124 deletes **all `~/.m2/repository`**. E126 condenses again. |
| E127–191 | Rebuild still fails. E129/131 remove explicit versions, E133 changes plugin management, E135 removes parent; E137 edit fails. E143 restores parent. E149/151 change web-module inheritance to Boot directly; E154 now reports missing local module versions as well. E155 restores project parent; E157 imports Boot BOM. E161 adds compiler source/target 21; E167 normalizes formatting. E170 explicitly manages starters; E174 removes root Boot plugin; E178 adds the same Maven Central endpoint as a purported mirror, then E182 removes it. E184/188 pin versions again; E190/191 fails. |
| E192–194 | Agent says it cannot complete and attributes missing webmvc 3.2.5 to environment/Maven access. E193 (00:42:53) denies with build failure, incomplete scan, 25 unknown identities, Java configuration failure and Boot downgrade/configuration failure. E194 injects that evidence. |
| E195–246 | E197 restores parent 4.0.6; E201/205 remove module pins and E207 removes explicit starter management, but older BOM/property/framework choices remain. E209/210 progresses to a startup-test failure: `SystemPropertyUtils` lacks `ESCAPE_CHARACTER` (`NoSuchFieldError`), consistent with mixed framework generations. E211 returns parent to 3.2.5. E214 empty-string replacement fails; E218 removes framework property; E226–236 add module-local properties/pins, E240 pins web Boot plugin. E244 again blames environment and declines completion. E245 (00:46:17) repeats the substantive failed checks; E246 injects feedback. |
| E247–273 | Removes module pins/properties, restores parent 4.0.6 at E255 and root Boot property 4.0.6 at E258. E260/261 build succeeds. E262 uses nonexistent OSV `--sbom-path` option; E263 reports usage error. E268 successfully generates CycloneDX aggregate BOM; E270/271 uses valid `--sbom` and gets vulnerability evidence, including Jackson 3.1.2. E272 obtains JSON dependency-tree evidence. This is real local recovery and better evidence acquisition. |
| E274–302 | JSON property becomes 20240303. E276 inserts `com.fasterxml.jackson.core` core/databind 2.19.1 management; E278 attempts structural repair, but E281 build fails with duplicated `dependencies` tag. E282 edit fails, E284 reads actual POM, E286 repairs nesting; E288 fails and E290 removes an empty block. E292/293 builds successfully. E294 regenerates BOM; E296/297 still reports Jackson 3.1.2 vulnerabilities. E298's narrow tree query yields no useful matches. E301/302 shows **`tools.jackson.core`** core/databind 3.1.2, exposing why the `com.fasterxml` override did not affect the actual dependency. |
| E303–371 | After that evidence, E303/305 again downgrade parent/property to 3.2.5; E307 removes Jackson overrides. Repeats version-management edits, plugin pin removal, explicit webmvc management (E325/329), BOM removal (E339), web property addition/removal (E344/348). E352 plugin edit fails. E354 lists Boot cache; E356 deletes all cached Boot artifacts; E358 fails. E360 restores BOM; E364 pins webmvc 3.2.5; E366 still fails. E368 `dependency:get` uses reversed packaging/version fields; E369 requests version `jar`, extension `3.2.5`. E370/371 HTTP HEAD for the intended POM returns **404, text/html, NoSuchKey**. |
| E372–404 | E372 removes web starters; E374/375 produces missing Jakarta validation/Spring HTTP/web/Boot compilation symbols. E376 restores starters; missing webmvc version returns. E380 removes service Spring context; after E384 explicit web pins, E387/388 fails service compilation (`org.springframework.stereotype`, `Service`). E389 adds `spring-boot-starter`; E391/392 returns to missing webmvc artifact. E393/395 downgrade parent/property to 2.7.18; E397 removes web pins. E399 fails missing webmvc version; E401 again deletes entire Maven cache; E403/404 repeats missing version at web POM line 29. |
| E405–406 | Final assistant message admits inability to complete and explicitly admits the final downgrade conflicts with the task. It nevertheless calls the issue environmental, says Maven Central shows the POM exists without a supporting successful lookup, and says it cannot run OSV despite its earlier usable SBOM scans. E406 (00:58:35) allows termination at the bound with deterministic acceptance explicitly false. |

Final [Git state](evidence/gate2-orchestrated-run-20261006T002206Z/git-state.txt) is still the baseline HEAD: three modified tracked POMs and one untracked downloaded POM; no target commit is evidenced. [Final diff](evidence/gate2-orchestrated-run-20261006T002206Z/final.diff) shows Boot parent/property 2.7.18, compiler source/target additions, commons-text/JSON in dependency management instead of inherited direct declarations, removal of root Boot plugin, and service `spring-context` replaced with `spring-boot-starter`. The web starter coordinate remains `spring-boot-starter-webmvc`. These changes do not establish application preservation or completed remediation.

## 5. First material divergence

**Before the hook**, the first evidence-interpretation failure is E22's success claim despite E17's extraction failure and exit 127. Nevertheless, independent E23 proves that the narrow library edit was a valid improvement.

**After that verified improvement**, the earliest material divergence is **E27**, confirmed by successful editor observation E28. There is no intervening authoritative release/compatibility lookup, vulnerability-to-version justification, or permission to downgrade. E30 immediately ties the change to missing management for the retained webmvc coordinate. E57 then pins that coordinate to 3.2.5; E60 confirms resolution failure. The available evidence supports an unjustified cross-family strategy and retained incompatible coordinate. It does not establish what hidden belief caused the choice.

The later stages reinforce, rather than replace, this finding: treating absent coordinates as a cache problem; retaining a downloaded error page; repeatedly modifying parent/BOM/module declarations; temporarily restoring 4.0.6 without aligning its dependencies; returning to 3.2.5 even after a fully working 4.0.6 build; and finally 2.7.18. The first condensation, E83, occurs **after** E27 and numerous failed builds. Condensation cannot explain the initial divergence.

## 6. Stop Hook cycle-by-cycle analysis

### Attempt 1: improved evidence exercised; unjustified strategy change

E23/E24 delivered all **23 remaining identities, severities, coordinates and current package versions**, zero unknown and zero new prohibited findings. The failed check was only target resolution. These details match the attempt-1 report; no truncation of the identity set was found. This materially exceeds Task-04's first feedback, which gave 22 remaining and hygiene failure without identities/versions.

The agent correctly treated the previous completion as insufficient and resumed dependency work. Its subsequent POM choice did not follow from the evidence: no returned finding requested Boot 3.2.5, and the contract prohibited that downgrade. The feedback supplied enough information to investigate the six affected packages and their dependency paths. Full fixed-version recipes were unnecessary and would change the responsibility split.

**Assessment:** evidence-driven reassessment PARTIAL (continued work); local repair substantial but inefficient; strategy changed in an unjustified direction; completion judgment POOR at E22 and more candid at E192. Unsupported environmental attribution first appears explicitly in E192.

### Attempt 2: policy response is temporary and incomplete

E193/E194 returned seven failed checks: build/test/startup; fresh scan; target improvement; target resolution; no-new comparison; protected Java configuration; Boot version policy. It identified all 25 unknown targets using baseline versions and Boot baseline 4.0.6/current 3.2.5. The full report additionally preserves cached missing-artifact output and OSV XML parsing failure on the downloaded POM. **Those detailed build/XML errors and the Java tuple were not included in the concise hook message.** The review must not pretend they were.

There was a direct response to Boot policy: E197 restored the parent. It did not remove the old BOM/property/framework combination or the added Java configuration. The resulting startup failure at E210 was new evidence, distinct from artifact absence. The agent responded by reverting the parent at E211, then continued explicit-version/module-property repair. It neither cleaned the downloaded POM nor acquired a complete scan before the next stop.

**Assessment:** evidence-driven reassessment PARTIAL; local repair YES; sustained strategy reassessment POOR; strategy persistence despite contradiction PROVEN. Java/scan failure response inadequate. E244 accurately admits noncompletion but repeats an unsupported environment explanation.

### Attempt 3: genuine temporary recovery, then relapse

E245/E246 repeat the same seven failed checks and 25 unknown identities. The persisted report is fresh (different tree digest and command timings), but it adds no successful acceptance result; its missing-artifact and XML-extraction causes repeat attempt 2.

This cycle does more than repeat blindly: E247–261 aligns parent/property/module inheritance sufficiently for a successful build. E262's invalid scanner flag is repaired through SBOM generation and `--sbom`. E276–293 repairs a newly introduced XML mistake and restores build success. E297 and E302 provide fresh contradictory evidence: Jackson remains 3.1.2 under `tools.jackson.core`, despite overrides for a different group. Yet E303/305 reintroduce the failed forbidden strategy. Added Java settings and the downloaded POM persist; no independent acceptance boundary passes.

**Assessment:** evidence-driven reassessment MIXED locally; local repair YES; strategy reassessment temporary; sustained recovery POOR. New scan/tree evidence was obtained but not converted into a constraint-compliant strategy. The final environmental explanation discounts the agent's own successful builds and security scans.

### Attempt 4: proper bounded failure, partly honest final statement

E405 honestly says the task cannot be completed and identifies the final build failure. That is better outcome calibration than repeated assertions of success. Its cause attribution is poor: 404/NoSuchKey supports missing coordinates; the alleged Maven Central website confirmation has no observed support; a tool-capability inability is contradicted by previous scans and shell access. Calling the problem unresolvable is not demonstrated.

E406's ALLOW means only that the three-denial experiment bound has been exhausted. The runner reads final validation separately and returns 2. No fourth denial, extra recovery cycle or deterministic acceptance is implied. This is successful enforcement of the experimental stop rule.

### Feedback quality decision

The transport improvement was exercised successfully. Attempts 2/3 unambiguously identified a task-invalid strategy and unavailable security comparison. They did not include every raw diagnostic, but the agent could read files, execute builds/scans, and inspect HTTP responses; its own observations exposed the core incompatibility. Missing feedback is **not proven as the cause**. More hook text is not justified merely by failure. Keep the existing mechanism and ownership boundaries. The concise “new prohibited: 0” count on incomplete scans requires its surrounding unavailable-comparison/UNKNOWN text; it must not be quoted in isolation as a pass.

## 7. Spring Boot and `spring-boot-starter-webmvc` investigation

### A. Task-05 evidence

The baseline build downloaded `spring-boot-starter-webmvc:4.0.6` and passed. Downgrading to 3.2.5 caused missing version management (E30); explicit 3.2.5 caused missing artifact (E60). E81 wrote an unvalidated 554-byte response to a `.pom` filename. All later deterministic scans report XML syntax failure at line 6: `<hr>` closed by `</body>`. E371 reports HTTP 404, `content-type: text/html`, `x-amz-error-code: NoSuchKey` and the precise missing object key.

Supplemental **read-only local inspection**, distinct from automatically published evidence, confirms the remaining untracked file is a 554-byte HTML 404 page with `<title>404 Not Found</title>`, an nginx body and padding comments; it has no Maven `<project>` document. SHA-256: `e791ccfcfee9c0d299d07474d9bfcbfcbebf1181323be601220c8a823062ab99`. The final Git capture lists the file but tracked `final.diff` does not include its bytes. The captured creation/scan errors already establish the substantive defect; this local check confirms its exact content. No evidence shows the agent read the body or installed it as a valid Maven artifact. **It created and retained the error page; intentional acceptance of HTML as valid XML is not proven.**

E368 is a separate probe defect: `dependency:get -Dartifact=org.springframework.boot:spring-boot-starter-webmvc:jar:3.2.5` reverses version/packaging. E369 explicitly requests `/spring-boot-starter-webmvc/jar/spring-boot-starter-webmvc-jar.pom` and `.3.2.5`, so that command cannot establish the intended coordinate's availability. E370 does probe the intended URL correctly.

### B. External verification, fetched 2026-10-07

| Authoritative source | Review-time result | Conclusion |
| --- | --- | --- |
| [Maven Central webmvc metadata](https://repo.maven.apache.org/maven2/org/springframework/boot/spring-boot-starter-webmvc/maven-metadata.xml) | HTTP 200; versions start at 4.0.0-M1; 4.0.6 listed; no 3.2.5 or 2.7.18 | This is a later Boot-family starter, not a Boot 3.2.x coordinate. |
| [Exact webmvc 3.2.5 POM](https://repo.maven.apache.org/maven2/org/springframework/boot/spring-boot-starter-webmvc/3.2.5/spring-boot-starter-webmvc-3.2.5.pom) | HTTP 404; HTML error body | Intended artifact absent on Central, consistent with Task-05's HTTP evidence. |
| [Exact webmvc 4.0.6 POM](https://repo.maven.apache.org/maven2/org/springframework/boot/spring-boot-starter-webmvc/4.0.6/spring-boot-starter-webmvc-4.0.6.pom) | HTTP 200; valid Maven project coordinates | Baseline coordinate exists. |
| [Exact web 3.2.5 POM](https://repo.maven.apache.org/maven2/org/springframework/boot/spring-boot-starter-web/3.2.5/spring-boot-starter-web-3.2.5.pom) and [Boot 3.2.5 documentation](https://docs.spring.io/spring-boot/docs/3.2.5/reference/html/using.html) | POM HTTP 200; documented MVC starter is `spring-boot-starter-web` | Normal Boot 3.2.x MVC starter differs. |
| [Boot 4.0 first application](https://docs.spring.io/spring-boot/4.0/tutorial/first-application/index.html) | Uses `spring-boot-starter-webmvc` | Official documentation corroborates family distinction. |
| [Maven dependency:get reference](https://maven.apache.org/plugins/maven-dependency-plugin/get-mojo.html) | Artifact format is groupId:artifactId:version[:packaging[:classifier]] | Explains E368/E369's malformed probe. |

**Inference:** the observed missing-artifact response is explained by an invalid coordinate/version combination, not by proven proxy/Maven/environment failure. A 404 alone cannot disprove every possible intermediary issue; metadata, working baseline downloads, successful unrelated downloads, correct 4.0.6 builds and current authoritative sources make that environmental attribution unsupported here. This diagnosis is not a remediation recipe or permission to change starter families: downgrading remained forbidden regardless of whether a different starter could compile.

## 8. Repetition and recovery

Counts below come from event arguments, not rendered-log repetitions. They count invocations/attempted edits; editor calls can fail without changing a file.

| Activity | Count / evidence |
| --- | --- |
| All actions | 193: 70 terminal, 123 file editor |
| File editor | 31 views, 84 replacements, eight insertions; ten error observations |
| Agent `mvn clean install` | 48 total: nine plain, 39 with `-U`; three successes (observations E15, E261, E293), 45 failures |
| Build calls by interval | Before hook 1: 1; hook 1→2: 24; hook 2→3: 4; hook 3→4: 19 |
| `mvn clean verify` | Zero agent invocations; five independent captured executions (baseline + four validator attempts) |
| Webmvc-related editor attempts | 25 with the coordinate in old/new arguments; includes failed E53 and broad blocks. Additional shell probes are separate. |
| Maven cache deletions | Four terminal calls: E77 selective webmvc/BOM directories; E124 entire repository; E356 Boot subtree; E401 entire repository again |
| Direct network probes/downloads | Two curl calls: E81 body download; E370 HEAD. One malformed `dependency:get` at E368. Normal Maven builds also download artifacts. |
| Security evidence | Five agent OSV invocations: two recursive source scans, one invalid SBOM flag, two valid SBOM scans. Two CycloneDX generations; three dependency-tree calls. |

Repeated parent/BOM-management work is visible at E88/100/135/143 (parent removal/restoration), E102/157/207/339/360 (BOM removal/import/rewriting), and E197/211/255/303/393 (parent family changes). Multiple versions and repositories were modified without rechecking whether the central artifact existed. E73→75 is a reasonable narrow experiment after cached-failure feedback; continued retries after forced update, deletion and repeated missing-coordinate results provide little new information. E309 and E313 repeat the same failing build separated only by a POM view. Cache removal cannot supply version management absent from the selected BOM.

Not all repetition is unproductive: E210 adds a distinct linkage failure; E261 restores the build; E263 teaches valid scanner usage; E271/297 supply security evidence; E281→293 repairs XML; E302 supplies actual Jackson coordinates; E371 supplies HTTP existence evidence. The failure is **poor use of those observations and relapse**, not total absence of investigation.

The runner explicitly enables native `stuck_detection=True`. No stuck-interruption/nudge event appears in the 407-event stream; the run ends through normal Stop Hook bounds, not iteration exhaustion or a stuck status. All terminal calls have `is_input=false/reset=false`, return completed exit codes, and none shows the Task-03 pager problem. The model pauses with noncompletion messages at E192/E244/E405, but does not sustainably interrupt the failed strategy. Section 13 explains why native exact-pattern detection is not a general engineering-strategy evaluator.

## 9. Context and condensation assessment

Eight recorded condensations occur at **E83, E126, E169, E213, E257, E300, E343 and E386**. The exporter retains their position/kind but omits payloads. This permits temporal analysis, not claims about the exact active model context.

| Earlier available information | Later contradiction / response | Defensible conclusion |
| --- | --- | --- |
| No downgrade, E1; baseline parent visible E11 | Downgrade E27, before any condensation | Initial constraint violation PROVEN; condensation as initial cause NOT PROVEN |
| Java constraint E1; Java settings read repeatedly | Source/target additions E161; ignored policy failures E194/E246 | Configuration nonadherence PROVEN; loss of numeric Java constraint NOT PROVEN |
| Exact 23 identities and package versions E24 | Speculative Boot family change; later wrong-group Jackson override | Poor evidence use PROVEN; whether those details were lost after condensation UNRESOLVED |
| Missing version/artifact E30/E60 and repeated builds | Repeated management/cache actions before and after condensations | Persistence PROVEN; cannot distinguish memory loss from bad interpretation by timing alone |
| Boot policy feedback E194/E246 | Parent corrections E197/E255; subsequent reversals E211/E303 | Some feedback uptake PROVEN; blanket claim that feedback was forgotten is unsupported |
| Valid 4.0.6 builds E261/E293; Jackson tree E302 | Immediate downgrade E303; final environmental explanation | Contradiction PROVEN; semantic integration failure is an inference, hidden context loss UNRESOLVED |
| No-downgrade rule | E405 explicitly acknowledges violating it | Rule is present in the final observable account; universal constraint amnesia is contradicted |

Native summarization exists (section 13), but a native capability's existence does not guarantee perfect retention. Conversely, eight condensations do not prove lost constraints. No custom memory layer or condenser changes are justified by this run. The observational gap is acknowledged rather than filled with inferred hidden reasoning.

## 10. Attribution matrix

Statuses apply to the precise concern, not to an entire product. **PROVEN** = directly established; **PARTIAL** = some supporting evidence with limits; **NOT PROVEN** = the claimed cause/gap is unsupported; **UNRESOLVED** = the available record cannot settle it.

| Owner | Concern | Status | Evidence and limit |
| --- | --- | --- | --- |
| A. Model / agent | Bad engineering strategy and unsupported environmental attribution | PROVEN | E27 forbidden downgrade; repeated nonexistent coordinate; E192/E244/E405 blame environment; temporary 4.x success discarded. |
| A. Model / agent | Stale model knowledge as specific cause | UNRESOLVED | Family/coordinate mistakes fit that hypothesis, but observable behavior cannot establish training knowledge or hidden rationale. |
| A. Model / agent | Inadequate sustained reassessment | PROVEN | Partial corrections and SBOM/tree investigation occur, then forbidden strategy returns. |
| B. OpenHands harness/runtime | Completion interception and continuation capability | PROVEN | Four hooks; three matching environment feedback messages; subsequent actions in same conversation; independent failure status retained. |
| B. OpenHands harness/runtime | Missing stuck detection / mandatory native intervention failure | NOT PROVEN | Detection enabled; source implements narrower patterns than varied POM/build churn. No proven triggering pattern was missed. |
| B. OpenHands harness/runtime | Condensation caused forgotten constraints | UNRESOLVED | Payload/active-context details absent; earliest divergence precedes condensation. |
| C. Stop Hook / deterministic feedback | Improved identity/version transport used | PROVEN | E23/E24 include all 23 current identities; E193/E194 and E245/E246 include 25 unknown identities and Boot evidence. |
| C. Stop Hook / deterministic feedback | Bad/missing feedback caused failed strategy | NOT PROVEN | Policy direction and scan incompleteness explicit; no feedback prescribed downgrade. Raw build/scan/Java detail is less rich than report, but central failure was independently observable. |
| D. Task prompt / contract | Ambiguous permission to downgrade or change Java | NOT PROVEN | E1 explicitly prohibits these. Exact Java-configuration equality is stricter than the natural-language numeric-version reading; that distinction is real and documented, not silently changed. |
| D. Task prompt / contract | Insufficient evidence access | NOT PROVEN | OSV exposed and used; shell/editor available; returned remaining identities support investigation. No guaranteed successful solution or feasibility proof follows. |
| E. Tooling | Agent source scans initially incomplete; malformed probe/flag use | PROVEN | E5/E17 local snapshot resolution; E263 invalid flag; E369 reversed artifact arguments. These are not evidence that working scanning/network tools were absent. |
| E. Tooling | Missing browser or missing security tool caused failure | NOT PROVEN | CLI preset omits browser, but shell/curl and later SBOM scan work. No demonstrated need for an additional tool. |
| F. Environment | Maven Central/proxy failure caused missing webmvc | NOT PROVEN | Artifact-specific 404/NoSuchKey, successful other downloads and baseline/temporary builds; external metadata corroborates invalid coordinate. |
| F. Environment | Broad local cache mutation | PROVEN | Four deletion calls, two whole-cache deletions. Persistent damage outside this run is UNRESOLVED; do not attribute unrelated failures without evidence. |
| G. Validator | Incomplete scan correctly becomes UNKNOWN and prevents acceptance | PROVEN | Attempts 2–4 fail comparisons; all targets unknown; no Task-03 false-resolution result. |
| G. Validator | Hygiene classifier misses downloaded error-page POM | PROVEN (narrow gap) | All hygiene checks pass; filename regex does not recognize arbitrary downloaded `.pom` files. Scan/build still fail; no false overall acceptance. Not changed here. |
| G. Validator | Java FAIL proves Java runtime changed | NOT PROVEN | Tuple comparison catches additional 21-valued keys. Whether broader semantic equivalence should be accepted is a separate policy-design question, not this review's authorization. |
| G. Validator | Validation bug caused remediation failure / false acceptance | NOT PROVEN | Independent build, scanner and Boot failures are valid regardless of Java/hygiene qualifications. |
| H. Evidence/logging | Blank README and Vertex metadata fields | PROVEN | Shell substitution and child-process environment scope defects; isolated reporting fix in section 12. |
| H. Evidence/logging | Loss of essential action/hook/report chronology | NOT PROVEN | Complete 407-event sequence, pairing and hashes, all per-attempt JSON/logs. |
| H. Evidence/logging | Exact active context and untracked-file bytes absent from repository bundle | PROVEN limitation | Condensation payloads omitted intentionally; tracked diff excludes untracked HTML bytes. Supplemental read-only inspection confirms HTML; core causal/outcome conclusions remain auditable from captured observations. |

## 11. Task-03 / Task-04 / Task-05 comparison

Compared only after independently reconstructing Task-05. Sources: [Task-03 analysis](GATE2-STOP-HOOK-TASK03-ANALYSIS.md), [Task-03 capture](evidence/gate2-stop-hook-task03-20261004/README.md), [Task-04 analysis](GATE2-STOP-HOOK-TASK04-ANALYSIS.md), and [Task-04 capture](evidence/gate2-stop-hook-task04-20261005/README.md). Baseline/final JSONs and all four retained hook records for each historical task were checked against those analyses. Historical overwritten per-attempt arrays remain UNKNOWN.

| Dimension | Task-03 | Task-04 | Task-05 |
| --- | --- | --- | --- |
| Baseline targets | 24 | 24 | 25 |
| First completion state | Passing build, Boot 3.2.0 downgrade; reported 0 remaining, earlier full scan coverage unavailable | Passing build, 22 remaining, hygiene failure; historical exact resolved count unavailable | Passing build, 2 resolved / 23 remaining / 0 unknown, Boot 4.0.6 |
| Hook evidence quality | Failure names/counts; pre-hardening coverage interpretation weak | Hardened UNKNOWN/comparison semantics; identity/version details absent | Identities/current versions exercised; per-attempt complete reports retained |
| Initial progress | Actual security progress not reliably quantified | Remaining 22→13 after first denial; exact earlier resolved arrays unavailable | Two direct targets demonstrably resolved before first denial |
| Response to feedback | Corrects parent downgrade, then unrepaired malformed XML/pager problem | Makes partial security progress, persists with rejected downgrade | Temporary parent corrections/build recovery; repeated downgrade relapse |
| Build preservation | Final malformed POM; FAIL | PASS at every hook | PASS at hook 1; FAIL at 2–4; two interim successes |
| Scan coverage | Final all six extracted packages filtered; claimed 24 resolved not trustworthy | Final complete; 11 resolved / 13 remaining / 0 unknown | Complete initially; final incomplete with 25 UNKNOWN |
| Boot constraint | Parent corrected; older BOM remained outside old check | Final 3.3.1 downgrade | 4.0.6→3.2.5 at E27; final 2.7.18 |
| Java constraint | PASS | PASS | Configuration FAIL after adding source/target 21; numeric version remains 21 |
| Strategy reassessment | One policy correction; poor later recovery | Library changes without correcting Boot strategy | Real temporary build/SBOM recovery, then abandonment |
| Unproductive actions | Reversals/cache deletion; pager-trapped terminal attempts | Repeated OWASP/config/cache/update actions | 48 install builds, 45 failures; four cache deletions; repeated parent/BOM edits |
| Final deterministic state | BOUNDED_FAIL; old reported zero findings not remediation proof | BOUNDED_FAIL; 13 remaining, 30 new prohibited, Boot/hygiene FAIL | BOUNDED_FAIL; build/scan/Java-configuration/Boot FAIL; new findings unknown |
| Completion judgment | Repeated success claims despite build failure | Four completion claims despite security/policy failures | First false success; later candid noncompletion but false environmental explanation |
| Evidence completeness | Observable excerpts/hashes; overwritten attempts | All hooks/messages; raw trajectory retained locally; overwritten attempts | Full observable event export + all four JSON/log pairs; metadata defects and intentional context omissions |

Same target commit does not guarantee identical vulnerability data across dates: Task-05's additional baseline identity relative to Task-04 is `CVE-2026-47884|org.springframework:spring-webmvc`. No normalized success-rate/statistical claim is justified from these few evolving experiments. **Task-02 remains infrastructure-confounded and is not a clean convergence comparator.**

## 12. Evidence-capture audit

| Capture requirement | Audit result |
| --- | --- |
| Observable trajectory | 407 ordered records; all 193 action/observation pairs present; E0–E406 contiguous |
| All hooks / feedback | Four Stop events E23/E193/E245/E406; three matching injected feedback messages E24/E194/E246 |
| Per-attempt JSONs and validator logs | Four of each; readable, substantive checks; final log/report agree with attempt 4 |
| Baseline / final validation | Present; final `validation.json` byte-identical to attempt 4 |
| Startup / verify / execute / combined logs | Present; Vertex project/location and SDK banner available; execution footer preserves result |
| Final Git state/diff/stat | Present; baseline HEAD, three modified POMs, untracked downloaded POM. Diff is tracked-only. |
| Manifest/hash integrity | Export SHA-256 matches; all 407 raw source files still exist locally and match manifest hashes |
| Run identity / bounds / metadata | Task/branch/control commit/model/bounds populated; README five fields and metadata Vertex fields blank |

### Exact metadata defect and isolated correction

The original run had five README `printf` format strings enclosing Markdown backticks inside **double quotes**. Bash performs command substitution on the enclosed `%s`, removes the placeholder and leaves blank fields. Single-quoted format strings preserve literal backticks and substitutions through `printf` arguments.

The parent fresh-run shell recorded `${VERTEXAI_PROJECT:-}` and `${VERTEXAI_LOCATION:-}`, but environment resolution occurred in child Startup/Verify/Execute shells. Exports do not propagate back to the parent. The values are proven present in all three captured stage logs. A small deterministic fix was justified, and **remote commit `c67b6e2ece41fee650a93a035ef3337a0d3e80a9` already supplied it**: source the existing shared environment resolver in the parent and use single-quoted README format strings. This review retains that fix exactly; it does not add another environment or logging mechanism.

The initial stale local checkout did not contain that commit. A local publication-only alternative reading stage banners was developed and passed offline checks, but was removed during reconciliation because the existing remote fix addresses the proven defect. Relative to remote `85b05b05`, the final review changes **only analysis and handoff documentation**. [Fresh-run publication](../../../scripts/openhands/openhands-gate2-fresh-run.sh) is byte-identical to that remote version.

**No historical Task-05 evidence is repaired or rewritten.** Task, stage, exit and environment are independently recoverable from the original bundle, so these defects do not undermine the analysis. Existing `baseline.json` also retains the generic hardcoded `experiment=openhands-gate2-task-01` label; actual `taskBranch`, target path and task-id disambiguate it. That separate cosmetic legacy label is documented, not changed.

### Real limits, without a logging redesign

The exporter is an observable projection, not a restorable model context: reasoning fields, raw LLM responses, observation metadata and condensation payloads are deliberately excluded. It retains no reviewed condensation summaries, so this review cannot settle context retention. The final tracked diff omits untracked bytes; the HTML finding has supplemental local read-only confirmation plus captured creation/parser/HTTP evidence. Referenced temporary validator artifact paths are not a promise those directories survive; embedded command outputs in JSON retain the decisive diagnostics. None requires a new planner, full private-context publication or a broad logging overhaul.

### Validation of this review

The retained metadata fix was validated offline using the shared resolver and extracted publication function, temporary output/log directories, a verified nonexistent test task and automatic push disabled. Stubbed gcloud responses exercised explicit Vertex settings, Google Cloud project fallback, configured gcloud fallback and POC defaults. Tests checked populated metadata, literal Markdown field values and unchanged failure status; `bash -n` passed. No actual gcloud operation, startup, smoke call, agent, validator, Maven build or scan was executed. The earlier local alternative also passed five publication tests, but is not the final implementation.

Review checks passed for local Markdown links, event references, action/observation pairing, build counts, per-attempt outcomes and exact hook-feedback transport. All 26 Task-05 capture files and 58 target-workspace files matched the review hash snapshots; all 407 raw event hashes also matched their original manifest. `git diff --check` passed. Final source comparison confirms the orchestration script matches remote `85b05b05` exactly. Target inspection used read-only file access; no remediation was modified. Existing unrelated nested-workspace changes remain excluded.

All 18 external source links were checked: 17 returned HTTP 200; the deliberately cited nonexistent webmvc 3.2.5 POM returned the expected HTTP 404.

## 13. Targeted external OpenHands research

Research was limited to mechanisms relevant to observed behavior. The official **v1.50.0 source tag** resolves to `dcf401af7a9a302ef92cb7d092e1df9bb659daa5`. Current upstream HEAD observed during review was `91ac058a08fd6365286fc8c5628f35a5f41ff300`. The four inspected stuck-detector, thresholds, hook processor and summarizing-condenser files were byte-identical across those revisions. This establishes no relevant difference in those files, not identity of every installed dependency or all upstream behavior. Task-05 logs and pinned execution command establish the tested SDK/tools version; source research is not a rerun.

- **Stuck detection:** [v1.50.0 detector](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-sdk/openhands/sdk/conversation/stuck_detector.py) scans a recent 20-event window and tests repeated action/observation equality, repeated action/agent-error patterns, monologue and alternating patterns. Equality is stricter than “another failed Maven build,” including action/observation content and an action thought field. This review does not inspect that private field. Ordinary failing shell commands are terminal observations, not automatically `AgentErrorEvent`s. The context-window-error detector is a TODO returning false; Task-05 does not exhibit such an error-only loop. Varying edits, output timings and interspersed observations make noninterruption understandable; no mandatory missed trigger is proven.
- **Thresholds:** [v1.50.0 types](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-sdk/openhands/sdk/conversation/types.py) defaults to four repeated action/observation pairs, three action errors, three monologue messages and six alternating-pattern entries. Stop Hook feedback and intervening actions are materially different from consecutive monologue. Changing thresholds is not justified by the run.
- **Stop semantics:** [hook processor](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-sdk/openhands/sdk/hooks/conversation_hooks.py) returns should-stop plus feedback, prioritizing additional context on denial. [Local conversation](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py) handles continuation and persistence. Task-05 independently proves actual injected messages and resumed actions, rather than merely inferring them from documentation. Product-owned bounds are implemented by the inspected control hook/runner, not assumed to be native acceptance policy.
- **Condensation:** [default condenser](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-sdk/openhands/sdk/context/condenser/llm_summarizing_condenser.py) uses summarization, default max size 80 and keep-first four, with explicit hard-reset handling. [Default preset](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-tools/openhands/tools/preset/default.py) selects this condenser and disables browser tools in CLI mode. These defaults do not reconstruct exactly what Gemini saw after each Task-05 condensation. E0 exposes terminal, file editor, task tracker, finish and think tools; the agent used only terminal/editor actions. No additional planner or memory implementation is indicated.
- **Terminal failures:** [terminal observation definition](https://github.com/OpenHands/software-agent-sdk/blob/v1.50.0/openhands-tools/openhands/tools/terminal/definition.py) carries command exit status and renders it to the model. A tool observation with `is_error=false` can still have shell exit 1/127; it is not a successful Maven/security result. Captured Task-05 command text and exit codes preserve this distinction. No terminal reset was required by a demonstrated pager blockage here.

For explicit current-upstream comparison, the reviewed [current detector](https://github.com/OpenHands/software-agent-sdk/blob/91ac058a08fd6365286fc8c5628f35a5f41ff300/openhands-sdk/openhands/sdk/conversation/stuck_detector.py), [current thresholds](https://github.com/OpenHands/software-agent-sdk/blob/91ac058a08fd6365286fc8c5628f35a5f41ff300/openhands-sdk/openhands/sdk/conversation/types.py), [current hooks](https://github.com/OpenHands/software-agent-sdk/blob/91ac058a08fd6365286fc8c5628f35a5f41ff300/openhands-sdk/openhands/sdk/hooks/conversation_hooks.py) and [current condenser](https://github.com/OpenHands/software-agent-sdk/blob/91ac058a08fd6365286fc8c5628f35a5f41ff300/openhands-sdk/openhands/sdk/context/condenser/llm_summarizing_condenser.py) are pinned to the review-time revision. No claim that an SDK upgrade would fix Task-05 follows.

## 14. Independent ratings

| Dimension | Rating | Basis |
| --- | --- | --- |
| Investigation quality | MIXED | Real scans/POM inspection, later SBOM/tree/HTTP investigation; artifact-family verification too late and misinterpreted |
| Tool-choice quality | MIXED | Working editor, build, CycloneDX and curl capabilities; excessive builds/cache deletion and malformed probe/flag |
| Evidence interpretation | POOR | Empty partial scan treated as clean; absent coordinate treated as environment; wrong Jackson group override |
| Strategy quality | POOR | Forbidden downgrade first; repeated cross-family strategy despite 4.x build success |
| Evidence-driven reassessment | POOR | Temporary useful corrections do not persist; central assumption survives contradictory feedback |
| Recovery behavior | POOR | Local XML/flag repairs and interim builds, but final build/scan and policies regress |
| Constraint adherence | POOR | Repeated Boot downgrades; extra Java configuration rejected; no final behavior-preservation proof |
| Self-validation | MIXED | Genuine passing builds and later usable security scans, but incomplete initial scan mishandled and final state invalid |
| Completion judgment | MIXED | First success claim false; later noncompletion candid, causal explanation unsupported |
| Final outcome | POOR | BOUNDED_FAIL; no deterministic acceptance; 25 targets unknown finally |

Tool-state recovery from an interactive/pager failure is **NOT EXERCISED**. These are qualitative judgments for this run/configuration, not population-level model benchmarks.

## 15. Proven strengths

- Two target findings resolved through a small initial edit while build, scan coverage and policies remained valid.
- Independent acceptance overruled false initial completion and failed closed on incomplete subsequent evidence.
- Native hooks delivered report-backed feedback into the same conversation at the unchanged bound.
- Improved identity/version feedback and automatic per-attempt retention were actually exercised.
- The agent could correct editor/CLI/XML mistakes, temporarily restore the build and acquire SBOM/dependency-tree evidence.
- Final noncompletion was explicitly admitted; the harness did not promote that termination into success.

## 16. Proven weaknesses

- The first valid state was abandoned through an unjustified forbidden platform downgrade.
- Artifact-family and coordinate mistakes persisted after missing-version, missing-artifact, dependency-tree and HTTP evidence.
- Repeated broad POM/cache actions did not resolve the central incompatibility; removal of required dependencies introduced compilation failures.
- The agent retained an HTML response under a `.pom` name, breaking independent extraction.
- Java configuration and Boot failures remained unresolved; the final state cannot demonstrate preserved application behavior.
- Environmental/capability explanations overstated what the observations proved.
- Publication metadata had two deterministic defects; hygiene classification and context/untracked-content retention have narrow documented limits.

## 17. Remaining unresolved questions

Whether stale knowledge, attention, condensation or another model limitation caused the observed choices is unresolved. Whether a stronger model would converge under the same harness is untested here. Whether this exact target set has a fully constraint-compliant solution is not established by a failed run; this review does not implement a hidden reference remediation. Model availability recorded in the handoff was not rechecked.

Native stuck detection did not interrupt this strategy, but whether a different native configuration would improve outcomes without stopping useful local repair is untested. No bespoke reasoning loop is warranted. The Java tuple check is stricter than a numeric-version interpretation and hygiene detection misses arbitrary downloaded POMs; these limitations do not invalidate the independent build/scan/Boot failures or justify policy relaxation during review. Exact condensation retention remains outside the published observable evidence.

## 18. Recommendation and next experiment decision

1. **What failed?** Sustained autonomous engineering convergence: an initially valid partial remediation regressed to broken dependency management, incomplete security evidence and rejected platform/configuration changes.
2. **First material divergence?** E27, Boot parent 4.0.6→3.2.5 while retaining the later-family webmvc starter; E30 immediately exposes missing management.
3. **Did Stop Hook work?** Yes: three genuine report-backed denials, continuation and bounded termination, with final acceptance false.
4. **Did improved evidence transport work?** Yes: all remaining identities/current versions and later unknown identities/policy evidence arrived and are retained.
5. **Proven OpenHands harness capability gap?** No new required capability gap is proven by Task-05. Noninterruption by narrow stuck detection is observed, not proof of a missing general-purpose planner.
6. **Proven missing-tool gap?** No. Existing tools acquired build, security, dependency and HTTP evidence; misuse/nonuse does not prove absence.
7. **Proven validator gap?** A narrow hygiene-classification omission is proven, and Java semantic strictness is documented. No acceptance-integrity defect or validator-caused central failure is proven. Keep policy unchanged.
8. **Primary remaining problem?** Observable model/agent behavior and engineering judgment, yes; precise model-internal cause remains unresolved.
9. **Enough evidence to continue evaluation?** Yes. The complete observable trajectory and all four reports materially improve attribution over Task-03/04.
10. **Changes before a future Task-06?** The isolated metadata fix was justified and is already present in remote commit `c67b6e2e`; it is retained. No prompt, strategy, hook bound, runtime, validator or tooling expansion is justified by this failure. Preserve Task-05 evidence and do not reuse its failed remediation state.
11. **Another same-model Task-06 now?** **No.** The planned feedback/tool-exposure test has now been exercised. Another identical run without a new hypothesis has low incremental value. Proceed to the planned OpenCode comparison under the same task/independent-validator/model-availability constraints; retain stronger-model isolation as a later controlled option when available. This recommendation authorizes no new run in this review.

**CONTINUE EVALUATION** remains the adoption decision. Keep one autonomous coding agent responsible for investigation, implementation, strategy reassessment, recovery and self-validation. Keep the product/evaluation layer responsible for contract, independent acceptance, evidence retention and bounds. Add no custom planner, reasoning loop, remediation recipe, agent-helping AGENTS.md/Skills, forced implementation path or extra retries.
