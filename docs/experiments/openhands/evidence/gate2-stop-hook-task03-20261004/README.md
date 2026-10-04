# Task-03 Stop Hook evidence capture

Read-only review of the completed run on 2026-10-04. [Analysis](../../GATE2-STOP-HOOK-TASK03-ANALYSIS.md).

Source: `~/.openhands/gate2/task-03-stop-hook`. Conversation events: `conversation/2884fc07b9004a468e4114d05eb3efd4/events/event-*.json`. The actual attempt counter is `hook/attempt-count`, not a top-level file. Source files remain in place and are hashed in `manifest.json`.

| Capture | Content |
| --- | --- |
| `baseline.json` | Sanitized original baseline, embedded build/OSV observations and 24 findings |
| `validation.json` | Sanitized final report only; embedded failed Maven output and empty-coverage OSV output |
| `attempt-count`, `last-validator.log` | Final counter 4 and final validator check summary |
| `stop-hooks.json` | All four complete hook events, including exact decisions, commands, stdout, feedback, IDs and timestamps |
| `trajectory.jsonl` | 350 observable records: all 169 actions, 169 observations, eight messages and four hooks. Look up original `sequence` numbers; JSONL line numbers are not event numbers |
| `action-index.md` | Ordered action/message/hook index and occurrence of seven context condensations |
| `run-summary.json` | Exact final runner summary lines with source run-log line numbers |
| `integration-audit.json` | Run-log infrastructure-error pattern counts, hook decisions and missing-marker check; negative searches supplement positive report-backed hook evidence |
| `final.diff`, `git-state.json`, `untracked-files.json` | Read-only tracked diff against HEAD/baseline, branch/HEAD/status and contents of the three small untracked artifacts; no build output |
| `manifest.json` | Raw source/event/control-script/changed-target hashes and exported evidence hashes |
| `capture-checks.txt` | Integrity, event pairing, feedback, snapshot, link, secret-pattern and documentation checks |

The raw `run.log` is 1,572,959 bytes / 21,897 lines and includes duplicated renderings, context summaries, and verbose errors. It is not committed. Neither the entire persistence directory, `base_state.json`, caches, Maven repository, nor target build output is committed. Missing earlier validation reports/logs are not reconstructed. Referenced `/tmp/openhands-gate2-validation-*` directories were absent at review.

Extraction used Python's standard library and the existing `export-event-history.py` `project`/`scrub` functions, without changing or executing the harness. It added HookExecutionEvent projection locally in the capture command. Internal reasoning, opaque provider signatures, system-prompt/tool schemas, condensation summary text, observation metadata and full duplicate editor old/new file snapshots are omitted. Action arguments, visible messages, and hook events are retained. Observation text longer than 3,200 characters retains exactly the first 1,300 and last 1,900 characters, with original character count and explicit omission notice. Raw source hashes allow local verification. Cloud-project banners/credential patterns are redacted; ANSI control sequences in copied standalone text are removed. The extraction is an evidence projection, not a restorable conversation backup.

Git inspection used `git --no-optional-locks` and did not execute target files. Final diff uses zero context (`--unified=0`) to avoid whitespace-only patch context lines and captures five modified tracked POMs; the three untracked files are separately captured. All raw events, source reports/logs, relevant control scripts, and changed/untracked target files were hash-checked after capture. No agent, hook, validator, Maven build, or scan was rerun. No tool/session/runtime state was changed.

Historical limits: hook summaries retain failed-check names/messages and remaining count. They do not retain resolved arrays, all passing checks, or exact new-prohibited counts for attempts 1–3. These are UNKNOWN in the analysis. A final `passed=true` subcheck is recorded faithfully even where its evidence limits the conclusion: empty scan coverage, parent-only Boot evaluation, and leftover artifacts must not be concealed by the status labels.
