# Recommendation

## Decision: A — proceed with A2 + narrow A1 + OSV

The strengthened evidence supports proceeding to a bounded next design phase
with Maven resolution as the application-effective authority, a narrow Boot BOM
component for release/management provenance, and conservative OSV advisory
interpretation.

A2 passed the original four cases and seven expanded real Maven executions,
including negative path removal and multiple forms of application control. A1
reliably explains managed defaults and advisory ranges but still cannot resolve
applications. deps.dev corroborated the hosted starter graph and advisory keys,
yet supplied no fact required to reach a verdict that Maven/BOM/OSV could not;
therefore decision B is not supported. The remaining gaps are important for
production design but no longer block this feasibility choice, so decision C is
also not warranted for the stated experiment.

Proceeding does not mean choosing releases by finding counts or claiming
compatibility. The next phase must invoke Maven's own full version semantics,
exercise repository/auth/profile/import edge cases, run candidate builds/tests,
and independently scan the complete resolved candidate application.
