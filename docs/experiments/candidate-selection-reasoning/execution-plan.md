# Bounded execution plan

No step in this plan has been executed.

## Stage 0 — qualify and freeze scenarios

1. Verify branch/commit and isolate a new experiment directory.
2. Create minimal Maven fixtures in disposable workspaces; do not modify
   production or OpenHands projects.
3. Use existing Maven/BOM/OSV infrastructure to establish baseline graphs,
   findings, credible strategy mechanisms, and validation commands.
4. For R4, search for and prove a real reproducible compatibility failure. For
   R5, prove a stable live incomplete/contradictory advisory or explicitly lock
   a timestamped real-response replay.
5. Write sealed expectations before any agent run, hash them, and remove them
   from the agent-visible workspace.

## Stage 1 — minimal reusable harness

Add a separate `candidate_selection_reasoning` experiment package containing:

- task/evidence/decision schemas;
- thin adapters over `BomResolver`, `MavenResolver`, and `OsvClient`;
- an append-only recorder;
- an agent runner with generic tools and resource bounds;
- an independent validator in a separate process/workspace;
- an evaluator that compares traces and validation with sealed expectations.

No adapter may rank releases or encode vulnerability IDs, preferred versions,
or strategy ordering. Deterministic unit tests cover schema validation, evidence
isolation, failed tool calls, status separation, revision links, and leakage of
hidden expectations.

## Stage 2 — pilot and controls

Run one non-scored plumbing task to verify recording and isolation. Then run R1
and R2 once with fixed model/configuration parameters. Inspect whether tools
accidentally reveal shortlists or expectations. Repair harness defects only;
never change expectations to fit agent output. Re-run invalidated pilots and
retain failure evidence.

## Stage 3 — full bounded experiment

Run R1–R5 with the same agent configuration and clean context per task. Return
independent validation after each submission, permitting at most two revisions.
Capture time, calls, tokens, network/cache use, Maven time and evidence size.
If budget expires, record the decision as incomplete rather than extending one
case selectively.

## Stage 4 — independent evaluation

1. Validate every submitted strategy, including rejected candidates when they
   carry decisive factual claims and budget permits.
2. Apply the reasoning rubric without seeing model-internal reasoning.
3. Compare against sealed expectations and classify defects.
4. Separate agent, validator, environment, source-data and harness failures.
5. Produce a cross-case report: discovery coverage, selection quality, revision
   behavior, calibration, reliability, and unsupported conclusions.

## Exit decisions

- **Proceed:** one agent shows traceable discovery, comparison and revision in
  all mandatory mechanism classes with no high-severity safety claim.
- **Narrow/retest:** useful behavior exists but a bounded tool, fixture, or
  evidence gap prevents a conclusion.
- **Do not proceed:** repeated premature commitment, failure to revise after
  contradiction, or unjustified safety claims persist despite adequate tools.

One successful run is feasibility evidence, not reliability proof. Any later
reliability claim requires repeated runs or multiple seeds, separately approved.
