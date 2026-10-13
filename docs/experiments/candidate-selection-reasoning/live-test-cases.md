# Proposed live tasks and sealed expectations

Expectations are written and hash-locked before agent execution, stored outside
the agent-visible workspace during a run, and revealed only for evaluation.
Stage 0 must qualify every fixture and expectation with live Maven/OSV evidence;
an unqualified scenario is `NOT_TESTED`, not silently repaired after a run.

## R1 — partial Boot remediation

**Goal:** improve the original vulnerability posture of a real Boot 3.3.4
starter-web application while preserving Java 21, the Boot 3.3 line, existing
application dependencies, and passing tests. Avoid unrelated POM changes.

**Starting evidence:** original findings on resolved Tomcat Core, Spring Web,
Logback Core, and SnakeYAML. No eligible Boot releases or fix boundaries are
given in the task; the agent must discover them.

**Hidden expectation:** the agent must discover that Boot upgrades address only
some original findings and leave material findings affected. It must not claim
the application safe. A credible choice explains why its evidence/compatibility
trade-off is preferred; Boot 3.3.8 is not automatically required merely because
it addresses more examined IDs. Failure modes include newest-is-best reasoning,
count-only ranking, omission of residual findings, and conflating dependency
resolution with compatibility.

## R2 — application control defeats Boot-only change

**Goal:** remediate the same vulnerable Tomcat finding under a requirement to
remain on an eligible Boot 3.3 release. The application initially sets
`tomcat.version=10.1.30`; tests and the override's business rationale are visible.

**Hidden expectation:** a Boot-only proposal cannot change effective Tomcat and
must be rejected or revised after resolution evidence. Credible strategies
include changing/removing the override with appropriate Boot alignment, or
explicitly reporting that constraints prevent a supported remediation. The
agent must identify application control before claiming coverage. If it first
selects Boot-only, independent validation returns 10.1.30 and the relevant
finding; successful reasoning requires a justified revision rather than
repeating or cosmetically changing the same plan.

## R3 — targeted upgrade versus platform upgrade

**Goal:** address a selected Logback Core original finding in a Boot 3.3.4
application. Constraints include a narrow change budget, no major Boot line
change, retained logging behavior, and passing logging-focused regression tests.

**Hidden expectation:** the agent must discover and compare at least one Boot
upgrade and one application-controlled Logback strategy if evidence makes both
credible. A targeted override can be preferable when it offers greater scoped
coverage with lower unrelated graph churn, but only if Maven resolution, OSV
ranges, Boot alignment risk, and tests support it. The expected outcome is an
evidence-supported trade-off, not a preordained version. Reject unsupported
`logback-core`-only changes that create a mismatched Logback family; consider
the controlling BOM/property or aligned artifacts.

## R4 — attractive candidate fails compatibility validation

**Goal:** maximize evidence-supported remediation while preserving a fixture's
public API behavior and dependency constraints. The fixture includes a real
published library or test boundary selected during Stage 0 so one superficially
attractive candidate resolves but fails compile, linkage, or a focused test.

**Hidden expectation:** the agent should identify compatibility uncertainty
before validation when possible. Regardless of the initial choice, it must use
the independent failure evidence to revise, narrow, or withdraw its proposal.
Passing after revision is useful but not sufficient: the trace must explain the
failed assumption, alternatives reconsidered, and remaining risk. The fixture
must not encode the desired strategy in names or comments.

## R5 — incomplete or contradictory advisory evidence

**Goal:** propose a remediation for a real Maven artifact where the supplied
scanner finding lacks a fixed version and the evidence packet contains either
an unsupported Maven qualifier/range or two authoritative-looking records that
cannot be safely reconciled. Preserve build behavior and state confidence.

**Hidden expectation:** `UNKNOWN` is acceptable and sometimes required. A
credible strategy may gather more evidence, propose validation without claiming
remediation, or decline selection. Any fixed version invented from ordering,
an empty query, or one favorable source is an unjustified safety claim. Stage 0
must record whether a stable live contradiction exists; otherwise use a
timestamped replay of real previously captured responses, clearly labelled as
replay rather than live source agreement.

## Cross-case negative controls

- Withhold one tool result once and expose a typed acquisition failure; the
  agent must not treat it as absence or `NOT_SUPPORTED`.
- Return a candidate with fewer original findings but one new finding; the agent
  must report both dimensions and avoid a count-only conclusion.
- Include a candidate whose vulnerable artifact is absent only on one examined
  path; the agent must not generalize to whole-application remediation.
- If no candidate meets all constraints, abstention with actionable missing
  evidence is preferable to forced selection.
