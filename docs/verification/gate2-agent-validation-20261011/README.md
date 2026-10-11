# Gate 2 agent-accessible deterministic validation verification

Date: 2026-10-11. Branch: `openhands-poc-evaluation`.

## Architecture and implementation

`validate-remediation` is a no-argument, session-PATH command installed by the existing OpenHands runner. The runner fixes the target checkout, saved baseline, scanner executable, and run-owned evidence root in the terminal environment. The command calls the same `openhands-gate2-validate.sh` / `DeterministicValidator` / `OsvScanner` path used by the Stop Hook, but writes to a unique `self-validation/validation-<UTC>-<suffix>/` directory and does not invoke the Stop Hook.

The OSV backend now derives expected Maven coverage from all non-generated `pom.xml` files in the current repository and matches that scope against OSV's successful per-POM dependency-extraction lines. Missing POMs convert an otherwise clean/findings result to `INCOMPLETE_FATAL_FAILURE`. Coverage is retained in the scan report and a standalone coverage artifact. This is repository-derived; no five-module constant exists.

Persistent invocation evidence includes `validation.json`, `validator.log`, `execution.json`, `evidence-integrity.json`, the full validator workspace, raw OSV JSON/stdout/stderr, normalized scan, per-attempt execution evidence, Maven request/coverage evidence, build logs, events, diff, and validation failure details. Scanner staging temp files remain disposable. Stop Hook reports, attempt counters, baseline state, other run evidence, and shared Maven caches are not cleanup targets.

## Automated requirement matrix

| # | Requirement | Test/evidence | Result |
|---:|---|---|---|
| 1 | All expected POMs, clean | `test_multimodule_scan_uses_fixed_scanner_without_reactor_deploy`; launcher integration | PASS |
| 2 | All expected POMs, findings | `test_complete_multimodule_scan_with_findings_reports_findings` | PASS |
| 3 | Root-only zero findings incomplete | `test_multimodule_root_only_zero_findings_is_not_clean`, `test_root_only_zero_finding_scope_is_incomplete` | PASS |
| 4 | Omitted module incomplete | `test_omitted_recursive_module_is_incomplete` | PASS |
| 5 | Extraction failure incomplete | `test_task10_failed_resolving_message_is_incomplete_even_with_zero_findings`, `test_partial_findings_with_resolution_errors_are_incomplete` | PASS |
| 6 | Empty/malformed success not clean | `test_success_exit_with_empty_or_malformed_json_is_not_clean` | PASS |
| 7 | Scanner executable/command failure | `test_configured_scanner_missing_fails_closed`, `test_empty_results_from_non_successful_execution_are_not_clean` | PASS |
| 8 | Scanner timeout | `test_scanner_timeout_is_retryable_failure_with_logs` | PASS |
| 9 | Maven failure fails validation/readable output | existing `build_test_startup` validator contract plus launcher-retained Maven stdout/stderr integration | PASS |
| 10 | Missing/invalid baseline explicit | `test_agent_visible_launcher_retains_missing_baseline_failure`; JSON parsing fails closed into retained infrastructure log | PASS |
| 11 | Terminal PATH discovery/execution | `test_importing_runner_does_not_import_legacy_agent`; `test_agent_visible_launcher_runs_real_validator_and_retains_isolated_evidence` | PASS |
| 12 | No baseline/target CLI parameters | no-argument launcher integration test | PASS |
| 13 | Complete persistent evidence | launcher integration plus evidence-integrity report | PASS |
| 14 | Raw OSV/log paths readable after return | launcher integration | PASS |
| 15 | Stop reports/counters unchanged | launcher integration sentinel and Task-19 attempt count remained `4` | PASS |
| 16 | POM/source unchanged | launcher integration hashes every tracked target file | PASS |
| 17 | Multiple invocations distinguishable | launcher integration retains two unique invocation directories | PASS |
| 18 | Failure does not end conversation/consume denial | launcher never invokes Stop Hook; controlled live conversation continued after exit `2`; disposable counter stayed `0` | PASS |
| 19 | Disposable temp cleaned | production scanner `TemporaryDirectory` lifecycle exercised by integration | PASS |
| 20 | Failure evidence preserved | missing-baseline and Task-19 failed-constraint evidence retained | PASS |
| 21 | Other evidence/caches unchanged | scoped unique evidence roots; no deletion code; sentinel/target assertions | PASS |

## Commands and proof classes

Validator unit/offline and launcher/runtime integration:

```text
uv run --with-requirements autonomous_oss_remediation_agent/requirements.txt --with pytest python -m pytest -q tests/unit/test_openhands_validation_integration.py tests/unit/test_autonomous_scanner_constraints.py tests/unit/test_target_comparison_coverage.py tests/unit/test_openhands_osv_session_launcher.py tests/unit/test_openhands_gate2_feedback_integrity.py tests/test_openhands_gate2_evidence_summary.py
61 passed, 1 skipped, 4 warnings, 12 subtests passed in 49.44s
```

A broader unit discovery command was also run:

```text
uv run --with-requirements autonomous_oss_remediation_agent/requirements.txt --with pytest python -m pytest -q tests/unit tests/test_openhands_gate2_evidence_summary.py
338 passed, 8 skipped, 17 failed, 128 subtests passed in 131.24s
```

The 17 failures are outside the changed Gate-2 validator/scanner/launcher modules: four autonomous-capability cases were affected by Cloud Shell login output/runtime-resource behavior, two legacy orchestrator expectations differ from current behavior, six tests call an intentionally disabled deterministic outcome-summary entry point, two provider declaration snapshots differ under the resolved ADK version, and three legacy validation-tool cases stop at Spring Boot run validation. They are recorded as broad-suite failures, not represented as passing or repaired by this change.

Real OSV Scanner 2.6.0 integration used `OsvScanner` against `tests/fixtures/maven-multi-module` with the local Maven repository server. It completed with findings and exact coverage:

```text
expected: pom.xml, service-a/pom.xml, service-b/pom.xml
scanned:  pom.xml, service-a/pom.xml, service-b/pom.xml
coverage complete: true
```

Retained real-scanner evidence (host-local, intentionally not committed):

- `/tmp/gate2-real-osv-20261011-2RSXX7/result.json`
- `/tmp/gate2-real-osv-20261011-2RSXX7/artifacts/scans/real-multimodule.json`
- `/tmp/gate2-real-osv-20261011-2RSXX7/artifacts/scans/real-multimodule.normalized.json`
- `/tmp/gate2-real-osv-20261011-2RSXX7/artifacts/scans/real-multimodule-coverage.json`

Actual no-argument Task-19 self-validation used the same PATH/env contract. It returned validator exit `2` (`validation_failed`) because `suppression_policy` failed, while Maven passed, OSV completed clean, all 26 original findings compared as resolved, and all five expected POMs were scanned. The failed constraint was correctly preserved rather than presented as acceptance. Evidence:

- `/home/kavya_parivarababu/.openhands/gate2/task-19-stop-hook/self-validation/validation-20261011T231937Z-clXOUx/validation.json`
- `/home/kavya_parivarababu/.openhands/gate2/task-19-stop-hook/self-validation/validation-20261011T231937Z-clXOUx/validator.log`
- `/home/kavya_parivarababu/.openhands/gate2/task-19-stop-hook/self-validation/validation-20261011T231937Z-clXOUx/evidence-integrity.json` (`complete: true`)
- `/home/kavya_parivarababu/.openhands/gate2/task-19-stop-hook/self-validation/validation-20261011T231937Z-clXOUx/workspace/artifacts/scans/validation-cycle-1.json`
- `/home/kavya_parivarababu/.openhands/gate2/task-19-stop-hook/self-validation/validation-20261011T231937Z-clXOUx/workspace/artifacts/scans/validation-cycle-1-coverage.json`

Representative agent-visible lines:

```text
==> Overall validation result: FAIL
==> Maven build/test result: PASS
==> OSV scan completed: YES (COMPLETED_CLEAN)
==> Maven POM coverage: expected 5, scanned 5
    Expected: pom.xml, task-common/pom.xml, task-domain/pom.xml, task-service/pom.xml, task-web/pom.xml
    Scanned:  pom.xml, task-common/pom.xml, task-domain/pom.xml, task-service/pom.xml, task-web/pom.xml
==> Failed constraints/checks:
    suppression_policy: Potential vulnerability suppression change detected
```

## Controlled live follow-up

One bounded Gemini 2.5 Flash conversation subsequently exercised the integration. The result is **PARTIAL**: the model invoked the command, observed real exit `2`, read raw OSV evidence, continued, and correctly reported complete 3/3 POM coverage plus the remaining finding. It did not separately open the coverage JSON, and a zero-finding/incomplete-coverage case was not exercised. See [the live verification record](../gate2-agent-validation-live-20261011/README.md).

## Evidence limits

- The offline launcher test uses deterministic fake Maven/OSV executables but executes the real launcher and real validator path. It does not prove the real OSV binary.
- The separate real-scanner test proves real OSV extraction, findings handling, coverage, and raw evidence for a three-POM fixture. It does not prove autonomous agent behavior.
- PATH discovery and post-failure continuation are now observed in one live conversation. Separate model reading of the coverage artifact failed, so full behavioral acceptance remains incomplete.
- Task-20 was not started.
