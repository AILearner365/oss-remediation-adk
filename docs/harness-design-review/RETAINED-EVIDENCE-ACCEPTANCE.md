# Retained-evidence acceptance exercise

This development-only fixture tests whether the model uses a real harness-issued reference to recover a decision fact omitted from a command excerpt. It does not run the OSS remediation orchestrator, evaluate vulnerability-remediation quality, or deliver anything. Run it separately from comparable frozen Experiment 1 evaluations.

The fixture creates a disposable repository and runs `emit_report.py` through `run_workspace_shell`. The command retains about 320 KB of stdout and returns a bounded tail with `stdoutReference`. The relevant `ADAPTER_MODE` line is around byte 140,000, outside that displayed tail. The generator is removed before the experimental workspace is created. The model receives the task, an incomplete excerpt, and the actual issued reference; it is not given the line's value or instructed to call retrieval. The full artifact remains under the run's `artifacts/commands` directory.

Offline capability check, from the repository root with the project dependencies installed:

```bash
python -m scripts.retained_evidence_acceptance
```

This mode starts no model. It makes one scripted query on the issued reference and verifies bounded match context, byte offset, provenance, exact one-call budget consumption, and full retained bytes. A pass establishes capability behavior only.

On a live-capable Linux machine with its usual ADK/Gemini credentials configured, from the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r autonomous_oss_remediation_agent/requirements.txt
.venv/bin/python -m scripts.retained_evidence_acceptance --live --model gemini-2.5-flash --workspace-parent /tmp/retained-evidence-acceptance
```

The `--live` flag is the explicit paid-model opt-in. It uses the existing one-agent ADK toolset and normal typed Cycle Intent checkpoint, with a single cycle, 80 shared tool calls, 60 model calls per turn, and a 2,000-character command excerpt. Research is disabled for this fixture; no target repository or delivery adapter is used. The command prints the retained workspace path.

Inspect `artifacts/events.jsonl`, `artifacts/agent/decision-journal.md`, and the command stdout artifact at that path. Live acceptance requires a model-chosen `retrieve_retained_evidence` call using the exact issued `stdoutReference` with a targeted query, a response containing the omitted mode, and an accepted Cycle Intent that cites and uses that recovered fact in its selection. Confirm the retrieval response precedes acceptance and that the model did not infer the answer from another source. The script's `liveTraceMeetsMechanicalCriteria` is a screening result; review the recorded reasoning and provenance before marking model adoption. A forced retrieval call or the offline scripted query does not satisfy live acceptance.

This exercise does not test the separate failed-capture recovery sequence or resolve unsupported parent/Jackson reasoning. Do not use a target PR as the fixture.
