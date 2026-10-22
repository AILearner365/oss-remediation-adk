# Task configuration and guarantees

Authority: native_remediation/contract.py DEFAULTS/load_task. An explicit approved
task value overrides a documented default only where supported. Nested Java/Boot
policy merges by key; lists replace, never append implicitly. Unknown fields,
unsupported scanners and conflicting inputs fail closed. The normalized immutable
task/digest is retained, not silently changed on recovery. Examples are syntax,
not fresh repository or model-cost authorization. No credentials in task values.

Classes: **A** mandatory per-task input; **B** default with approved override;
**C** discovered capability/environment; **D** non-bypassable guarantee.

| Setting | Class | Implemented input/default and boundaries |
| --- | --- | --- |
| Repository / base | A,D | repository owner/repo, base_branch, immutable 40-hex base_sha required; verify approved remote base; never push base |
| Objective / scope | A,B,D | goal required; policy.target_ids=[] plus max_remaining_findings=0 means all baseline findings must resolve, no introduced findings; original coverage retained. No severity-only filter implemented; HIGH/CRITICAL prose does not silently narrow acceptance |
| Java changes | B,D | policy.java.allow_change=false; allowed_versions=[] optionally pins numeric values. Compares effective Java properties and compiler source/target/release. Additional toolchain/runtime compatibility needs deterministic checks |
| Spring Boot | B,D | policy.spring_boot.patch=true, minor=true, major=false, downgrade=false. Explicit per-category overrides; checks root parent/BOM and resolved Boot coordinates by reactor module using retained graphs. Identical sets do not create artificial movements; changed multi-version sets without sufficient ownership remain INCONCLUSIVE, and provable forbidden downgrades FAIL |
| Other dependency movement | B,D | allow_major_upgrades=false, allow_downgrades=false; no forced upgrade recipe. Resolved package removals require allowed_removed_dependencies coordinates. Overrides/exclusions/replacements allowed within approved paths and resolved-graph/coverage/policy checks; special semantic constraints need explicit checks |
| Edit scope | B,D | allowed_paths=[pom.xml, **/pom.xml]; protected_paths/properties=[]; approved task may widen/change scope, never bypass exact-tree/path checks |
| Build/tests/compatibility | B,D | Maven clean install with tests; profiles=[]; no test-count regression; minimum_tests=0 enforced on baseline and candidate. tools.checks argv lists and constraints=[{description,check:argv}] are required invariants on BOTH baseline and candidate; failures are never ignored to permit model startup. No final-only check phase exists. Vulnerability-goal policy is compared after complete baseline/candidate collection. Free-text claims never substitute for checks |
| Scanner | D,C | scanner={type:osv,version:2.6.0}; tools.osv=OSV executable name/path, tools.maven=mvn. Version/coverage checked at execution. Other scanner versions/providers (including future Xray) require a separately verified adapter, not a permissive config switch |
| Scan arguments / coverage | D | Trusted all-packages/all-vulns OSV argv, no ignores; complete resolved reactor project-dependency graph, all scopes. Plugin/JDK/OS coverage not claimed; partial/error/unknown never PASS |
| SBRI | B,C | mode=auto (off/auto/on supported), pre_edit=true, executable=null. Discovery: explicit executable > tools.sbri_reference > PATH sbri. Root Boot applicability is bounded, not exhaustive reactor discovery. on attempts intelligence, not a mandatory Boot solution or clean-result gate |
| SBRI candidates | B | versions=[] OR ranges=[] (X.Y.Z / X.Y.x); scopes=[compile,runtime], max_candidates=12 (1..50). Native tool can supply validated candidate/scopes inputs. Defaults delegate release discovery to existing CLI; rank is security evidence, compatibility NOT_ASSESSED |
| SBRI cache | B,D | cache_seconds=3600; retry_seconds=60; backend_version=null (optional approved deployment version label, NOT an observed version probe). Cache identity includes tree, task/conversation, profiles, candidate/scopes/config, executable path/content hash/mtime and Maven/OSV executable identity. Fresh COMPLETE results reused; known INCONCLUSIVE results retried after cooldown, all within max_sbri_calls. CLI sbri --refresh refreshes completed calls; agent manages no cache flags. Interrupted/in-flight or uncertain-termination calls never automatically replay, even with --refresh. TTL bounds remote-data staleness but does not snapshot live advisory databases or hash a backend's entire dependency installation |
| Model / budgets | B,D | model=vertex_ai/gemini-2.5-flash; max_iterations=40 (<=1000), max_cycles=3 (<=10 independent attempts), max_runs=2 (<=5), command_seconds=900, validation_seconds=2400, task_seconds=7200, max_decisions=12, max_self_validations=4, max_sbri_calls=3. Positive bounded limits, zero automatic model retries; explicit model-cost authorization separate from delivery |
| Terminal waits / deadlines | D | Native PreToolUse terminal policy requires positive finite timeout <= command_seconds and remaining task admission budget; Ctrl-C/Ctrl-D/Ctrl-Z interrupts remain available after expiry. Native terminal timeouts bound foreground waits, not command lifetime or background descendants. Deterministic commands retain process-group timeout cleanup. task_seconds is an admission/evaluation deadline, NOT a hard wall-clock limit on run(). Iteration/recovery/Stop budgets remain native/bounded. Native hook infrastructure errors can fail open; direct SDK execute_tool is trusted-caller functionality bypassing action hooks. None of this provides P0 isolation |
| Guidance | B,D | skills=[dependency-remediation-decision,maven-dependency-evidence], project_context="". Optional evidence-driven-dependency-remediation replaces, never duplicates decision Skill. SDK native loading; no ambient user/public/project Skills or memory; immutable context checked on resume |
| Self-validation | D,B | Native validate_remediation always exposed; same validator, separate report/budget, cannot override task/policy or accept/deliver. Optional CLI self-validate; host authority isolation deferred |
| Research | C,B | Native terminal uses installed host tools/authorized network; tools.research_reference optional evidence reference, no special research framework or guaranteed web tool. Verify authoritative publication/compatibility, do not equate missing tools with unavailable versions |
| Network/proxies | C | Host PATH/Java/TLS/Maven configuration and proxy environment, no forced offline/Docker mode. Metadata records executable paths/SDK versions/proxy variable presence, never credential/proxy values; availability is not proof of successful access |
| Evidence/retention | D,C | Private task state, native conversations/events/stats plus automatic phase indexes/Git diff; separate baseline/attempts/self-validation/SBRI/journal/claims. No deletion or automatic publication; retention cleanup is an operator responsibility. No agent questionnaire or fabricated rationale |
| Workspace | C,D | Official LocalWorkspace(state/workspace), native subprocess TerminalTool; host execution, not isolation. Records outside repository do not protect against the same user. Authority isolation deferred; no bypass mode or sandbox.image |
| Delivery | B,A,D | Default delivery={mode:report_only}; draft_pr additionally requires repository,base_branch,draft:true,authorized:true matching approved task. Legacy destination-only policy remains unauthorized. Only independent exact-tree PASS may deliver; no merge, unrestricted push or push to base |
| Credentials / recovery | C,D | Discover existing ADC/gh environment only through trusted preflight, refreshed ADC >=300s, no keys printed/created. Immutable identity/evidence, native persistence/resume, bounded claims and positive remote reconciliation; unknown mutation never blindly retried |

Report-only runs still need an approved remote base and baseline coverage, but no
GitHub push/PR credential permission. Independent PASS yields VALIDATED and
deliveryStatus=NOT_REQUESTED; draft confirmation yields DELIVERED. Native finished
alone is neither. BOUNDED_FAILURE and BLOCKED do not mean vulnerability resolution.

Host authority isolation is explicitly deferred by product decision, not a
per-task configurable bypass. Preparation/build/model/acceptance/delivery are no
longer unconditionally blocked for that reason. The same-user host still cannot
protect records/credentials from agent/build code. Current tests use safe
temporary fixtures; no live model, network scanner or SBRI engine proof is claimed.

SBRI receives approved tools.profiles automatically through --profiles, and the
approved command timeout through --timeout. The agent-facing tool remains
versions/ranges/scopes only. Canonical profiles/scopes/release coverage must match
before intelligence is marked COMPLETE. Ordinary missing/malformed/partial output
is retained as UNAVAILABLE/INCONCLUSIVE, not zero findings; authority, task/tree
identity and cached-evidence mismatches still block. Existing normalized receipts
and persisted native agents are not silently migrated to changed defaults or
hook/tool configurations; prior evidence remains intact.
