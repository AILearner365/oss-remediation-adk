# Autonomous OSS Vulnerability Remediation — handoff

Continue on `autonomous-oss-remediation`; preserve `openhands-native-product`
at 11431b428a69f4525679bda5880bf0a0d05137bc and all previous evidence/history.

The selected framework is standalone OpenHands SDK/tools 1.55.1. LocalWorkspace
uses the actual repository path; native TerminalTool uses its normal persistent
host shell. Mandatory sandbox.image, Docker checks/launcher/cleanup and forced
network=none were removed. Existing bounded local command execution supplies
Maven/OSV and retains configured proxy variables. No new runner/framework/service.

The lifecycle implementation remains idle SDK creation/restore, deterministic
preparation, durable identity-bound COMPLETE, send_message/run, native Stop,
independent acceptance, report-only by default and authorized PASS-only exact-tree draft delivery. SDK owns history,
status and reasoning; application records only task/evidence/budgets/claims.
Retain all policy/scanner/coverage, intent/outcome/reassessment and delivery guards.

**Do not claim authority isolation.** State and credentials are outside the
workspace, but LocalWorkspace/TerminalTool and Maven execute as the host user.
They can access sibling state/home/credentials, create background processes, and
load repository code/plugins. A working directory is not a process/filesystem
boundary. No agent-facing acceptance/delivery tool is provided, which does not
remove that physical authority.

Authority isolation is unsupported in this deployment and explicitly deferred
by product decision on 2026-10-22. The legacy require_independent_authority
checkpoint now returns without blocking; all existing call sites remain for
future enforcement. This is not security proof or an alternate execution mode.
Baseline COMPLETE, evidence integrity, policy, model authorization, independent
deterministic Stop acceptance and exact-tree PASS-only delivery are unchanged.
See docs/OPERATIONS.md for actual prerequisites and first-run commands. A real
Gemini remediation is still unproven; no live run is authorized by this handoff.

Historical P1 correction checkpoint (superseded counts in readiness report):
the suite uses full `unittest discover -s tests_native`, including
the existing product/local/parity/SDK checks and new test_p1/test_sdk_p1 regressions.
Pinned SDK run: 70 passed, five optional Agent Server probes skipped (75 total).
Stdlib-only run: 60 passed, 15 expected skips. No paid inference or live analysis.
Real SDK tests cover idle persistence, retained Stop denial, evidence-tool use,
host workspace commands and persistent terminal invocation without inference.
Maven/OSV stand-ins and controlled outputs do not prove real analysis. The SDK
workspace command helper emits non-fatal ResourceWarnings in this installation;
vendor code is untouched.

See [operations](docs/OPERATIONS.md) and [proof map](docs/IMPLEMENTATION.md).
Behavioral alignment with reference e5d160cb is recorded in [POC parity](docs/POC-PARITY.md),
including Task 24/26 successes, Task 25 ADC failure and the later reused Task 26
export. General context plus two native Skills replace duplicated workflows;
material decision/outcome records are optional, with automatic native/Git evidence.
Self-validation and optional SBRI tools never accept, deliver or consume Stop attempts.
The existing SBRI CLI is not installed here; the adapter is fixture-verified only.
Task/config defaults and permitted overrides are in [configuration](docs/CONFIGURATION.md).
The unresolved decision is the mandatory authority requirement in the selected
same-user host environment, not SDK lifecycle support or image provisioning.
Do not invent infrastructure, weaken acceptance, run Gemini or create target PRs.

P1 corrections preserve strict baseline requirements and unchanged P0 refusal.
Boot comparisons use retained reactor-module ownership; ambiguous changed sets
do not pass. Approved Maven profiles flow into both SBRI entry points. Optional
SBRI failures retain bounded results, with checksummed TTL/cooldown reuse and
operator refresh; unknown execution never automatically replays. The actual
historical CLI parser is fixture-tested, but the SBRI backend remains unavailable.
Native PreToolUse bounds terminal foreground wait requests; task_seconds is an
admission/evaluation deadline, not a hard wall-clock process limit. These changes
do not resolve native hook fail-open behavior or P0 host authority. See the
[P1 proof map](docs/IMPLEMENTATION.md#p1-correction-status) for exact limits.
