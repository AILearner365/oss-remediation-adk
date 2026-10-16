# Evidence and decision-capture contract

## Agent-visible inputs

- Task ID, immutable goal, allowed scope, compatibility constraints, change
  budget, validation commands, baseline repository hash, and original findings.
- Generic tools only: inspect Maven model; enumerate published Boot versions;
  inspect Boot management; resolve an exact proposed POM change; query OSV by
  Maven package/version or advisory ID; request a validation submission.
- Tools return raw facts, provenance, timing, typed failures and uncertainty.
  They never recommend, rank, shortlist, or label a strategy preferred.

## Observable agent record

Every material decision event is append-only JSONL with:

- event ID, task/run/attempt IDs, timestamp, parent decision ID;
- fact or uncertainty discovered, source/evidence IDs, and confidence basis;
- candidate strategy created/updated/withdrawn, exact proposed changes, intended
  mechanism, assumptions, expected original/new/unknown finding effects;
- dependency and compatibility risks, required verification, rejected
  alternatives and rejection evidence;
- selection event with comparison set and preference rationale;
- revision event linking new validation evidence to invalidated assumptions and
  changed strategy fields;
- unsupported conclusions, tool failures, abstention, and unresolved questions.

The final proposal is a machine-readable Maven patch specification, not prose
alone. The experiment captures concise stated rationale; it does not request or
store hidden chain-of-thought.

## Independent evidence

The validator runs outside the agent context in a fresh disposable copy and
records separately:

- exact baseline/candidate POM diff and hashes;
- Maven effective model, dependency tree, selected versions and paths;
- active profiles, mediation, overrides, exclusions and graph diff;
- per-original advisory outcome with OSV contents/provenance;
- newly reported findings and unknowns separately;
- build, compile, focused tests, exit codes, logs and elapsed time;
- network/cache metrics, tool versions and source timestamps;
- validation status: `CONFIRMED`, `CONTRADICTED`, `INCOMPLETE`, or `ERROR`.

The validator never edits the agent's rationale or declares reasoning quality.
A harness error is returned as `ERROR`, not negative candidate evidence.

## Artifact layout

```text
evidence/<run-id>/
  manifest.json
  task.json
  sealed-expectation.sha256
  agent/events.jsonl
  agent/candidates.json
  agent/final-decision.json
  validation/attempt-1/{request,result,dependency-tree,build-test}.json
  validation/attempt-2/...
  evaluation/reasoning-quality.json
  evaluation/expectation-comparison.json
  metrics.json
```

Raw HTTP caches, local repository copies, JARs and build outputs are excluded
from retained evidence. Store bounded response excerpts or content-addressed
source records sufficient to reproduce conclusions, with credentials redacted.
