# Decisions required before implementation

1. **Agent runtime and model:** choose the single agent implementation, model
   version, temperature/seed behavior, authentication source, and token budget.
   These must be fixed in the run manifest; this design does not assume OpenHands.
2. **R4 fixture:** authorize Stage 0 to discover and qualify the exact real
   compatibility/conflict fixture. The failure mechanism must be reproducible
   and not revealed by fixture naming. No specific conflict is claimed yet.
3. **R5 evidence mode:** decide whether a timestamped replay of real advisory
   responses is acceptable if no stable live contradiction exists. Requiring
   live contradiction may make the case `NOT_TESTED` when sources converge.
4. **Validation mutation scope:** confirm that the validator may apply proposed
   POM edits only in disposable fixture copies and download Maven dependencies.
5. **Run count:** one run per task is enough for the initial feasibility question
   but cannot establish reliability. Decide whether repeated seeds/runs belong
   in this experiment or a later reliability phase.
6. **Original-finding snapshot:** lock whether findings come from the committed
   v2 evidence timestamp or are refreshed during Stage 0. Refreshes can change
   hidden expectations and must be frozen before agent exposure.

Implementation should not start until decisions 1–4 are resolved. Decisions 5
and 6 can use the recommended defaults: one scored run per task initially and a
fresh Stage-0 snapshot frozen with hashes.
