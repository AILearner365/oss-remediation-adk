# Controlled live `validate-remediation` verification

Date: 2026-10-11. Branch: `openhands-poc-evaluation`. Implementation under test: `c8a5622dc04775f49f74985379a59554a3915fe8`.

## Result

**PARTIAL.** One and only one live OpenHands SDK conversation ran with `vertex_ai/gemini-2.5-flash`. Gemini independently invoked `validate-remediation summary` as an unqualified terminal command, received the real validator's exit code `2`, continued after that failure, opened the retained raw OSV JSON, and correctly reported that validation failed with one remaining HIGH SnakeYAML finding. The validator completed a three-POM scan with exact 3/3 coverage. Gemini did not separately open the retained coverage JSON despite the explicit request, so that behavioral requirement failed. The completed-with-findings run did not exercise the zero-findings/incomplete-coverage distinction.

- Conversation: `ec608c4e-e15e-4890-8ee6-529c61a05cd0`
- Live elapsed time: `42.608` seconds
- SDK execution status: `finished`
- Model usage: 35,772 prompt, 1,508 completion, 1,123 reasoning, and 6,360 cache-read tokens; reported cost `$0.0127844`
- Validator exit/status: `2` / `validation_failed`
- OSV execution: exit `1`, `COMPLETED_WITH_FINDINGS`, scanner succeeded
- Expected and scanned: `pom.xml`, `service-a/pom.xml`, `service-b/pom.xml`
- Remaining finding: `GHSA-mjmj-j48q-9wg2` / `CVE-2022-1471`, `org.yaml:snakeyaml:1.33`, HIGH, fixed in `2.0`
- Stop Hook: not attached; official attempt counter `0 -> 0`; official sentinel hashes unchanged
- Integrity: complete, with no missing or inaccessible evidence
- Source isolation: baseline hash and every tracked fixture file unchanged

## Assertion record

| Assertion | Result | Supporting event or artifact |
|---|---|---|
| Gemini invoked `validate-remediation` | PASS | Action `808a3392-7e6e-48bd-bc37-9442e11e1361`: `validate-remediation summary` |
| Executable resolved through configured PATH | PASS | The same action used no path; observation `f695e4ea-340d-439f-91a6-55be6e6d1e30` contains real validator output and exit `2` |
| Real validator executed | PASS | Observation `f695e4ea-340d-439f-91a6-55be6e6d1e30`; `execution.json` records `validatorExitCode: 2` |
| All expected Maven POMs were scanned | PASS | `validation-cycle-1-coverage.json`: expected/scanned counts `3/3`, identical lists, `complete: true` |
| Zero findings were not confused with incomplete coverage | NOT EXERCISED | The actual scan was complete with one finding, not a zero-finding scan |
| Gemini read retained raw scanner evidence | PASS | Action `723c21d6-1a9d-472d-9422-9a3cafea4b2f` and observation `3ff2d821-8b28-47a8-82c1-7236d8a4f120` read the saved raw OSV JSON |
| Gemini separately read retained coverage evidence | FAIL | No action opened `validation-cycle-1-coverage.json`; it relied on the validator's 3/3 summary |
| Failed validation allowed continued investigation | PASS | Exit-2 observation `f695...` is followed by raw-evidence action `723c...` and a correct final response `1637c4bc-2a3f-4b77-81d0-b9905b9acc04` |
| Gemini distinguished findings from scanner failure | PASS | Final response says the scan completed with findings and validation failed due to the remaining target finding |
| Stop Hook isolation was preserved | PASS | `isolation.json`: counter `0 -> 0`, report hashes unchanged, `stopHookAttached: false` |
| Baseline and application sources remained unchanged | PASS | `isolation.json`: `baselineUnchanged` and `trackedSourceUnchanged` true; no changed tracked paths |
| Errors and raw evidence remained accessible | PASS | `evidence-integrity.json`: `complete: true`; raw JSON, stderr, execution evidence, validation JSON, and logs remain present |

The machine-readable version is [assertions.json](assertions.json).

## Evidence locations

The unique host-local evidence root is:

```text
/home/kavya_parivarababu/.openhands/gate2-live/validate-remediation-20261011T234125Z
```

It retains `events.jsonl` (the full sanitized nine-event observable trajectory), the SDK persistence directory, `status.json`, `final-assistant.json`, `isolation.json`, baseline and manifest, and the disposable workspace. The invocation directory is:

```text
/home/kavya_parivarababu/.openhands/gate2-live/validate-remediation-20261011T234125Z/harness-state/self-validation/validation-20261011T234230Z-5BYYv5
```

That directory retains `execution.json`, `evidence-integrity.json`, `validation.json`, `validator.log`, raw OSV JSON and stderr, standalone coverage JSON, normalized report, Maven request evidence, build logs, validation events, and repository delta. Large generated evidence is not duplicated in Git.

An earlier preparation-only directory, `validate-remediation-20261011T234030Z`, revealed that an ephemeral `uv` interpreter path disappeared after preparation. It made no model call and ran no live conversation. The harness was changed to create a run-local durable validator virtual environment before the single live run. Gemini also supplied the unexpected extra `summary` argument; the no-argument launcher ignored it and executed normally.

Applicable offline verification after adding the reusable live harness:

```text
63 passed, 1 skipped, 4 warnings, 12 subtests passed in 49.49s
```

Task-20 was not started.
