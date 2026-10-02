# Evidence-boundary acceptance catalogue

This development-only fixture tests whether the model uses a real harness-issued reference to recover a decision fact omitted from a command excerpt. It does not run the OSS remediation orchestrator, evaluate vulnerability-remediation quality, or deliver anything. Run it separately from comparable frozen Experiment 1 evaluations.

`667fff37` retains live run `run-20261002T193518Z-4037c96a`: the model chose the issued reference, queried `ADAPTER_MODE`, and retrieved `ADAPTER_MODE=stream` at byte 133211. The turn then completed normally with 78 shared calls remaining. There was no Intent submission or rejection. The fixture, unlike production, called `run_turn` only once and closed the session. This establishes autonomous targeted retrieval, not accepted decision use, checkpoint rejection, or exhaustion.

| Scenario | Fixture and acceptance boundary | Autonomous status |
|---|---|---|
| A. Retained command evidence | `--scenario retained-command`: a disposable repository runs `emit_report.py`; about 320 KB of immutable stdout is retained. A decision-critical `ADAPTER_MODE` line is omitted from the 2,000-character excerpt. The model receives the task, incomplete excerpt and actual issued reference, without the answer or a required retrieval call. Acceptance requires autonomous targeted retrieval, accepted Intent, a selected candidate consistent with the recovered setting, and provenance to the issued reference. | Live retrieval observed in `667fff37`; accepted selection unverified. |
| B. Incomplete-turn recovery | Offline regression retrieves successfully in turn 1 without submission, then accepts Intent on a bounded turn 2 in the same session. The live runner now continues naturally if a turn ends without submission. | Deterministic only. Record naturally occurring empty turns in live traces; never force one and call it autonomous behavior. |
| C. Partial-read/edit boundary | `--scenario partial-read-edit` offline uses a long, generic `settings.conf` with an unrelated trailing sentinel. It verifies continuation, missing/fabricated/stale receipt rejection and a targeted edit that preserves the sentinel. | Live model-choice fixture deferred; it would need additional execution-phase orchestration to judge the model's edit choice. Existing production capability tests cover legitimate complete rewrites. |
| D. Outcome freshness | Existing production integration regressions construct authoritative edits, previous/current check evidence, accepted Intent and Outcome. They distinguish checks before and after edits and expose check-state relation. | Live model-authored Outcome exercise deferred; building a separate Outcome runner would duplicate orchestration. Use a normal production trace when one becomes available. |

The runner accepts `--scenario` and `--trials 1..10`; every trial has an independent workspace and session. Only A has an explicit paid `--live` mode. C is offline-only. B is tested deterministically and observed opportunistically within A. D uses the production integration tests below. Each live result reports retrieval, no submission, rejection count, exhaustion, acceptance, selection consistency, source citation, trace path and terminal error separately. Its mechanical criteria are a screen, not proof of reasoning quality or a reliability rate.

Offline capability check, from the repository root with the project dependencies installed:

```bash
python -m scripts.retained_evidence_acceptance --scenario retained-command
python -m scripts.retained_evidence_acceptance --scenario partial-read-edit
python -m unittest tests.unit.test_evidence_boundary_acceptance tests.unit.test_autonomous_capabilities tests.integration.test_autonomous_orchestrator.AutonomousOrchestratorIntegrationTests.test_prior_cycle_scan_does_not_validate_corrective_edit_and_final_resolution_reconciles tests.integration.test_autonomous_orchestrator.AutonomousOrchestratorIntegrationTests.test_outcome_evidence_exposes_unrelated_removal_and_accepted_intent -q
```

This mode starts no model. It makes one scripted query on the issued reference and verifies bounded match context, byte offset, provenance, exact one-call budget consumption, and full retained bytes. A pass establishes capability behavior only.

On the user's GCP Cloud Shell with its existing ADK/Gemini credentials, from the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r autonomous_oss_remediation_agent/requirements.txt
.venv/bin/python -m scripts.retained_evidence_acceptance --scenario retained-command --live --trials 2 --model gemini-2.5-flash --workspace-parent "$PWD/autonomous-oss-remediation-workspaces"
```

The `--live` flag is the explicit paid-model opt-in. Start with two independent A trials; one trial is enough if cost is a concern. The runner uses the existing one-agent ADK toolset and normal typed Cycle Intent, one cycle, 80 shared tool calls, ten checkpoint attempts/continuation turns, 60 model calls per turn, the configured per-turn and overall time limits, and a 2,000-character command excerpt. An incomplete turn gets the production Intent retry message in the same session. Research is disabled; no target repository or delivery adapter is used. The command prints every retained workspace and trace path. A failed trial exits nonzero after printing its location and terminal error.

Inspect `artifacts/events.jsonl`, `artifacts/agent/decision-journal.md`, and the command stdout artifact in each workspace. Push only the relevant workspace's `artifacts/events.jsonl`, `artifacts/agent/decision-journal.md`, the command stdout/stderr logs and any small fixture result JSON for review. Exclude `temp/`, caches, credentials and unrelated generated files. Confirm the retrieval precedes acceptance and the selected candidate, not just some unrelated Intent prose, uses the retrieved setting with an accurate issued-reference citation. The mechanical result cannot establish arbitrary prose correctness; review the model's reasoning and provenance manually. A forced query or the offline scripted query is capability verification only. A few passes are not a statistical reliability guarantee.

This exercise does not test the separate failed-capture recovery sequence or resolve unsupported parent/Jackson reasoning. Do not use a target PR as the fixture.
