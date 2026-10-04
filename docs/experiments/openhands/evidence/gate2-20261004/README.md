# Gate 2 evidence capture

Captured 2026-10-04 from local persisted files, without contacting or starting OpenHands. Analysis: [GATE2-TRAJECTORY-ANALYSIS.md](../../GATE2-TRAJECTORY-ANALYSIS.md).

- `events.jsonl`: observable projection of all 366 SDK event files in conversation `c06a12ed24424277a8200f309ca6cdc8`. Event sequence numbers are unchanged; line number = sequence + 1. Complete projected tool observations include command output, errors, exit status, and file-editor results. No additional output truncation was applied by this export.
- `conversation-index.md`: readable index of all actions and user/assistant messages; observation references point into JSONL. It is an export convenience, not another source.
- `baseline.json`: saved pre-agent OSV baseline and embedded build evidence.
- `validation.json`: saved recovery validation only, with 7 resolved / 17 remaining. The earlier native 10 / 14 validation summary is in conversation E00135. A distinct native validator JSON was not recovered.
- `manifest.json`: source paths and SHA-256 hashes of original events/documents, plus hashes of exported JSONL/documents. Hashes establish the bytes captured, not external authenticity of scanner claims.
- `capture-checks.txt`: lightweight export/integrity checks performed for this capture; no remediation tests or scans were rerun.

Source event directory:

```text
~/.openhands/agent-canvas/dev_conversations/c06a12ed24424277a8200f309ca6cdc8/events
```

Source deterministic documents:

```text
~/.openhands/gate2/task-01/baseline.json
~/.openhands/gate2/task-01/validation.json
```

Reproduce the event projection into a **new**, non-runtime destination:

```bash
python3 scripts/openhands/export-event-history.py \
  "$HOME/.openhands/agent-canvas/dev_conversations/c06a12ed24424277a8200f309ca6cdc8/events" \
  /tmp/gate2-observable-export
```

The small generic exporter uses only Python's standard library. It reads event JSON directly, requires a new output directory outside the source directory, rejects unknown event kinds, and never imports the SDK, acquires its locks, calls its API, or writes runtime state. The two deterministic documents were loaded as JSON, passed through the same `scrub` function, and serialized with indentation; original/export hashes are recorded in the manifest. The readable index was generated from the projected events, pairing actions and observations by retained tool-call ID.

The projection intentionally excludes internal reasoning/thought fields, provider thought signatures (stripped from call IDs while retaining the call prefix), raw LLM responses, observation metadata, system dynamic context, tool schemas, and state stats values. Other state updates retain status/user-message IDs. Cloud project banners and credential-like fields/patterns are redacted. No profile, session key, environment file, conversation state file, or unrelated shell history was exported. Pattern redaction is not a universal secret detector; publication also received a content-pattern review. These omissions mean this is not a restorable conversation backup.

Original tool-output clipping, if present, remains. Source `/tmp/openhands-gate2-*` command/scan/diff artifact paths survive as provenance, but those directories were absent at capture, so their files are not included. No final diff has been invented from those paths. The SDK edit arguments and observations preserve the observable edit sequence. Existing shared `bash_events` were not copied because the SDK observations already supply this conversation's outputs and the shared directory includes unrelated sessions.

One exported system prompt contains OpenHands' own default repository-memory/testing instructions. Those are historical runtime evidence, not recommendations or instructions for this evaluation.
