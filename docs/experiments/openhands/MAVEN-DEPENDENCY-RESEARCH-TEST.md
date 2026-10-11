# Maven dependency research behavioral test

This investigation-only test gives OpenHands SDK 1.50.0 the existing general guidance, repository context, and `maven-dependency-evidence` Skill. It exports the exact `origin/main-runrunning` commit rather than copying a worktree, records the resolved full SHA and initial POM evidence, and fails if the agent edits the exported workspace.

## One live Cloud Shell run

Run from the `oss-remediation-adk` repository. The output directory must be new and outside the evaluated source workspace.

```bash
source scripts/openhands/openhands-cloudshell-env.sh
openhands_resolve_vertex_env
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
UV_CACHE_DIR="${UV_CACHE_DIR:-$HOME/.cache/uv}" uv run \
  --with 'openhands-sdk[vertex]==1.50.0' \
  --with 'openhands-tools==1.50.0' \
  python scripts/openhands/maven-dependency-research.py \
  --source-repo "$HOME/maven-multimodule-app" \
  --baseline-ref origin/main-runrunning \
  --output-dir "$HOME/.openhands/maven-dependency-research/$RUN_ID"
```

The runner resolves and records the baseline (currently `9ea1b0ed5ca255db0fc7c659d050896d3ed5db78`). It reads the dirty source repository only through Git object data; it never resets, cleans, or modifies that worktree.

## Artifacts and review

The chosen output directory contains `run-manifest.json`, `skill-delivery.json`, `status.json`, `events.jsonl`, `final-assistant.json`, `assessment.json`, before/after workspace manifests, `workspace-integrity.json`, the SDK `conversation/` persistence, and the isolated `workspace/`. The integrity report checks both the isolated workspace and the original source worktree. Artifacts written before model execution remain available after an exception. Inspect the summary with:

```bash
jq . "$HOME/.openhands/maven-dependency-research/$RUN_ID/assessment.json" \
  "$HOME/.openhands/maven-dependency-research/$RUN_ID/status.json" \
  "$HOME/.openhands/maven-dependency-research/$RUN_ID/workspace-integrity.json"
less "$HOME/.openhands/maven-dependency-research/$RUN_ID/events.jsonl"
```

## Boundaries and limitations

The run may use Maven repositories, vulnerability services, and ordinary web access available to the default agent; those results can change. It does not alter Maven caches or scanner policy. Skill configuration and trigger delivery are recorded separately and do not prove explicit use. The assessment is a conservative keyword index (`PROVEN`, `PARTIAL`, `NOT PROVEN`), not an automated judgment of hidden reasoning; a person must review the observable commands, results, and final answer. OpenHands/provider internals may not expose every token count, stop detail, or Skill invocation. Private reasoning is deliberately not exported, and redaction is best-effort, so artifacts should be reviewed before sharing.

A live run consumes Vertex AI Gemini 2.5 Flash tokens plus any external repository/scanner traffic, is bounded to 120 agent iterations by default, and may take several minutes. No live run is part of the offline test procedure.

Run offline coverage (no Gemini calls) with:

```bash
python -m unittest tests.test_maven_dependency_research -v
```
