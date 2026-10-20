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
| Spring Boot | B,D | policy.spring_boot.patch=true, minor=true, major=false, downgrade=false. Explicit per-category overrides; checks root parent/BOM and resolved Boot coordinates; ambiguous/unverified movements INCONCLUSIVE, not success |
| Other dependency movement | B,D | allow_major_upgrades=false, allow_downgrades=false; no forced upgrade recipe. Resolved package removals require allowed_removed_dependencies coordinates. Overrides/exclusions/replacements allowed within approved paths and resolved-graph/coverage/policy checks; special semantic constraints need explicit checks |
| Edit scope | B,D | allowed_paths=[pom.xml, **/pom.xml]; protected_paths/properties=[]; approved task may widen/change scope, never bypass exact-tree/path checks |
| Build/tests/compatibility | B,D | Maven clean install with tests; profiles=[]; no test-count regression; minimum_tests=0. tools.checks argv lists and constraints=[{description,check:argv}] enforce additional compatibility/behavior requirements. Free-text claims never substitute for checks |
| Scanner | D,C | scanner={type:osv,version:2.6.0}; tools.osv=OSV executable name/path, tools.maven=mvn. Version/coverage checked at execution. Other scanner versions/providers (including future Xray) require a separately verified adapter, not a permissive config switch |
| Scan arguments / coverage | D | Trusted all-packages/all-vulns OSV argv, no ignores; complete resolved reactor project-dependency graph, all scopes. Plugin/JDK/OS coverage not claimed; partial/error/unknown never PASS |
| SBRI | B,C | mode=auto (off/auto/on supported), pre_edit=true, executable=null. Discovery: explicit executable > tools.sbri_reference > PATH sbri. Root Boot applicability is bounded, not exhaustive reactor discovery. on attempts intelligence, not a mandatory Boot solution or clean-result gate |
| SBRI candidates | B | versions=[] OR ranges=[] (X.Y.Z / X.Y.x); scopes=[compile,runtime], max_candidates=12 (1..50). Native tool can supply validated candidate/scopes inputs. Defaults delegate release discovery to existing CLI; rank is security evidence, compatibility NOT_ASSESSED |
| Model / budgets | B,D | model=vertex_ai/gemini-2.5-flash; max_iterations=40 (<=1000), max_cycles=3 (<=10 independent attempts), max_runs=2 (<=5), command_seconds=900, validation_seconds=2400, task_seconds=7200, max_decisions=12, max_self_validations=4, max_sbri_calls=3. Positive bounded limits, zero automatic model retries; explicit model-cost authorization separate from delivery |
| Guidance | B,D | skills=[dependency-remediation-decision,maven-dependency-evidence], project_context="". Optional evidence-driven-dependency-remediation replaces, never duplicates decision Skill. SDK native loading; no ambient user/public/project Skills or memory; immutable context checked on resume |
| Self-validation | D,B | Native validate_remediation always exposed; same validator, separate report/budget, cannot override task/policy or accept/deliver. Optional CLI self-validate; live trust guard still applies |
| Research | C,B | Native terminal uses installed host tools/authorized network; tools.research_reference optional evidence reference, no special research framework or guaranteed web tool. Verify authoritative publication/compatibility, do not equate missing tools with unavailable versions |
| Network/proxies | C | Host PATH/Java/TLS/Maven configuration and proxy environment, no forced offline/Docker mode. Metadata records executable paths/SDK versions/proxy variable presence, never credential/proxy values; availability is not proof of successful access |
| Evidence/retention | D,C | Private task state, native conversations/events/stats plus automatic phase indexes/Git diff; separate baseline/attempts/self-validation/SBRI/journal/claims. No deletion or automatic publication; retention cleanup is an operator responsibility. No agent questionnaire or fabricated rationale |
| Workspace | C,D | Official LocalWorkspace(state/workspace), native subprocess TerminalTool; host execution, not isolation. Private authority records outside repository; mandatory host trust guard unchanged, no bypass or sandbox.image |
| Delivery | B,A,D | Default delivery={mode:report_only}; draft_pr additionally requires repository,base_branch,draft:true,authorized:true matching approved task. Legacy destination-only policy remains unauthorized. Only independent exact-tree PASS may deliver; no merge, unrestricted push or push to base |
| Credentials / recovery | C,D | Discover existing ADC/gh environment only through trusted preflight, refreshed ADC >=300s, no keys printed/created. Immutable identity/evidence, native persistence/resume, bounded claims and positive remote reconciliation; unknown mutation never blindly retried |

Report-only runs still need an approved remote base and baseline coverage, but no
GitHub push/PR credential permission. Independent PASS yields VALIDATED and
deliveryStatus=NOT_REQUESTED; draft confirmation yields DELIVERED. Native finished
alone is neither. BOUNDED_FAILURE and BLOCKED do not mean vulnerability resolution.

All live preparation/build/model/acceptance/delivery remains blocked because the
same-user host cannot protect trusted records and credentials from agent/build
code. Configuration does not waive that requirement. Current tests use safe
temporary fixtures; no live model, network scanner or SBRI engine proof is claimed.
