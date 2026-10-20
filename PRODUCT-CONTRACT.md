# Product contract — Autonomous OSS Vulnerability Remediation

Status: **local standalone SDK implementation; live execution BLOCKED on
independent authority, no live remediation proof**. Use SDK/tools 1.55.1,
not an Agent Server extension. Normal execution creates/restores a local native
conversation, prepares deterministically, gates on durable COMPLETE evidence, then
sends the task and calls run(). Missing evidence blocks initial/recovery execution.
No Docker image/launcher or offline-only networking is required. LocalWorkspace
and native TerminalTool execute on the host, not in a sandbox. Same-user shell/
build code can access trusted records and credentials outside its working directory;
the mandatory authority separation below is not established. Live build/acceptance,
model dispatch and delivery fail closed on that exact unsupported guarantee.
See [implementation](docs/IMPLEMENTATION.md) and [operations](docs/OPERATIONS.md).
Historical Milestone 1 smoke remains at f72e5308704960ee911f382f96bf0b7948435216.

## Outcome and operating model

Given an approved repository revision and a remediation objective, autonomously investigate, select and implement a credible solution, independently verify it, and report the outcome. The default report_only policy never pushes or creates a PR. Explicitly authorized draft_pr delivery publishes only an independently verified exact tree. If the goal cannot be met within policy/budget, return an evidence-backed bounded failure, not a fictional success. Java Maven OSS remediation is the first application.

**Lifecycle**: stable task/constraints -> deterministic baseline COMPLETE -> autonomous discovery and credible whole-goal strategies -> investigation/implementation -> reassessment and self-checks -> native Stop independent validation -> deny with evidence or verified outcome -> authorized delivery if requested. Preserve concise rationale at material decisions and concise final outcome/uncertainty, through native messages or optional structured records; no per-command questionnaire or mandatory pre-edit intent form.

**Invariants**:
- Goal over chosen strategy; no prescribed Spring Boot upgrades or forced recipe.
- Evidence over assumptions; verify decision-critical unknowns. A failed tool call does not prove capability is unavailable.
- Consider credible alternatives and actual dependency relationships (direct, managed, imported BOM, override, transitive, relocation/not-managed), not only scanner counts.
- A validation failure is new evidence and may require a **different** approach, not an automatic repeat.
- One autonomous reasoning/coding agent; no planner/executor multi-agent product.
- Agent self-validation does not replace a separately trusted, deterministic final acceptance gate.
- Carry contract, Git state, cycle intent/outcome, and validation feedback into bounded recovery without strategy momentum.
- Preserve enough traces to understand candidate choice, evidence quality and changes; never require revealing hidden model chain of thought.

## Native-first integration boundaries

Standalone native OpenHands SDK/tools 1.55.1 owns conversations, the agent loop,
events/state persistence, tools and hooks. The application uses its standard local
caller sequence, not a custom reasoning loop or remote service. Model configured:
`vertex_ai/gemini-2.5-flash`; configuration is explicit/replaceable. Prior smoke
used Server/SDK 1.55.1 and Canvas 1.27.1; standalone state is not automatically
registered in those services. Verify installed APIs, not upstream main assumptions.

Minimal integration responsibilities:
1. **Preparation/run**: initialize the idle native SDK conversation first; execute
   trusted deterministic preparation/baseline without inference. The supported
   caller then checks a durable COMPLETE receipt bound to native conversation,
   task/repository/base/tree/baseline digest before send_message/run. Resume checks
   the same receipt and native persistence; never infer readiness from messages.
   Missing/incomplete/stale evidence or failure blocks paid execution. Normal
   `start` includes this sequence; diagnostic `prepare` is not mandatory externally.
   Native hooks/tools are verified after lazy initialization before run.
   All configured tools.checks/constraints are required baseline and candidate
   invariants; failed checks are never ignored to permit startup. COMPLETE also
   requires matching reactor graphs/inventory, exact scanner coverage and the
   configured minimum tests. Vulnerability-goal comparison remains a subsequent
   acceptance decision, not a demand that the vulnerable baseline already be clean.
2. **Agent capabilities**: grant needed repository, shell, Maven, OSV/scanner, research and optionally SBRI/release-intelligence access with bounded permissions. Reuse/copy/rework experimental code freely; agent selects when to use capabilities. SBRI is a helper, not an obligatory Spring Boot strategy; current test scanner is OSV, production candidate JFrog Xray requires a separate adapter/verification.
3. **Independent validation**: apply task-specific acceptance contract to an immutable captured candidate Git tree and baseline. Check actual resolved dependency set and findings, remaining/new vulnerabilities, applicable upgrade policy, Maven build/tests and repository constraints. Explicitly distinguish scanner errors, incomplete coverage and unknowns from PASS. Ensure paths/dependency source are available as required. Record attempt evidence and provide actionable failure context through native Stop Hook; accepted completion requires proof for the exact conversation, approved base and validated tree.
4. **Delivery**: report_only preserves independent validation without remote writes. Explicitly authorized draft_pr after independent PASS binds output to the validated Git tree, verifies remote base/destination, uses a create-only branch/commit, and confirms an open **draft** PR identity. Preserve local claims and reconciliation; ambiguous remote mutation blocks, never blindly duplicates. Native hook-command failures cannot establish product success.
5. **Recovery/evidence**: use native conversation/events plus small durable task/intent/outcome/validation/delivery artifacts as needed, without reimplementing native history, task API, UI or lifecycle database. Keep secrets out of workspaces and committed artifacts. Avoid unrestricted retries.

### Mandatory pre-inference guarantees

Normal product execution must establish all of these through supported native
SDK facilities and the explicit trusted caller sequence: (A) preparation associated
with the initialized native conversation, (B) completion
before any Gemini inference, (C) failure prevents inference, (D) evidence bound
to that conversation, (E) recovery cannot silently skip/duplicate preparation,
and (F) preparation authority isolated from agent-controlled content/commands.
Preparation is deterministic code, never an agent-selected reasoning step.
Untrusted Maven build logic must not gain trusted evidence/credential authority.

A–E have an implementation through the standalone caller gate, durable receipt
and native SDK persistence, with scoped offline verification. F is **not satisfied**
by host LocalWorkspace/TerminalTool or local Maven. State/policy/preparation/
acceptance records and credentials remain outside the repository, but that is
organizational separation, not protection from the same user. No agent tool
provides acceptance/delivery operations; shell filesystem/process access is still
unrestricted. SDK lazy repository plugin loading can also execute repository code.
files.require_independent_authority blocks live dispatch, default untrusted builds/
acceptance and delivery before treating those records as independently trusted.
There is no override flag, new isolation design or weakened acceptance rule.
Safe fixtures may replace this guard to verify contracts, never as live proof.
The earlier remote limitations remain [historical evidence](docs/NATIVE-PREPARATION-BLOCKER.md),
not a blocker to the local SDK lifecycle APIs themselves.

## Inputs and outputs

Required task input: repository, approved base branch and immutable SHA, and remediation goal. Approved values override documented defaults where permitted; unknown inputs fail closed. Policy/checks describe additional hard constraints. Delivery destination and explicit authorization are required only for draft_pr. Credentials are never task values. See the implemented [configuration reference](docs/CONFIGURATION.md). Baseline is deterministic preparation, not a mandatory user-supplied CVE list.

Output: native event/action/observation trajectory and usage stats; automatic phase evidence with Git diff/tree and stable artifact references; concise material decision/outcome records when supplied (absence is explicit, never fabricated); baseline/resolved dependencies/scanner coverage; separate self-check and independent PASS/FAIL/INCONCLUSIVE reports; verified PR URL only when authorized, otherwise report-only, bounded failure or blocked result. See [parity/evidence](docs/POC-PARITY.md).

## Proven versus unproven

**PROVEN in native one-file smoke:** native conversation and Gemini execution, one Stop Hook invocation, exact one-file deterministic PASS, validated tree/base binding, successful draft PR #214, native/API visibility; no custom product API/UI/SQLite needed. Reference: `docs/experiments/openhands/OPENHANDS-NATIVE-WIRING-SMOKE.md` at parent commit.

**NOT PROVEN by smoke:** Maven/OSV validator under native Stop Hook; full goal remediation; cycles/denials on this adapter; agent reasoning quality; policy/scanner coverage; production durability/recovery; Canvas browser activity; secure production multi-user isolation. Earlier experiments support design but are not equivalent to production proof.

Known limits: same-user host authority cannot enforce the independent trust
guarantee, so normal live execution/acceptance/delivery remain blocked. Host network
and proxy settings are allowed, not forced offline; real Maven/OSV/research and
full remediation were not exercised. Persistent ADC and durable local claims
remain deployment responsibilities. Native command-hook infrastructure can fail
open but cannot itself establish product success. Background process quiescence
and production-grade security isolation are not claimed for host LocalWorkspace.
Historical smoke-specific iteration/whitelist restrictions are not acceptance
defaults for remediation. No live model or target PR is authorized here.
The P0 authority correction remains deferred; its unconditional guard is unchanged.
Native terminal wait policy is a PreToolUse check, not an isolation boundary.
task_seconds is a dispatch/tool-admission/evaluation deadline, not a hard
wall-clock kill switch for the native run or its background processes. See the
[configuration reference](docs/CONFIGURATION.md) for exact timeout/cache semantics.

## Implementation discipline

Preserve the existing implementation and useful historical evidence; extract only purposeful code. Follow installed OpenHands conventions. No custom server, UI, SQLite, lifecycle coordinator, second agent or competing orchestration engine. No gratuitous abstraction, recipes, forced alternatives or unrelated refactors.

Engineering has discretion over internal file layout and adapters. It must show concrete mapping from this contract to code and tests, and a short proof table (PROVEN/PARTIAL/NOT PROVEN). Do not declare success on unit tests alone. Security-sensitive operations must be checked before externally creating PRs or running model calls.

## Immediate execution boundary

Only code/documentation changes, focused offline checks and read-only native
capability inspection are authorized for this correction. No Gemini call,
runtime install/upgrade, target-repo edit, delivery PR or remediation run is
authorized. Product development is on `autonomous-oss-remediation`; the original
`openhands-native-product` branch and its implementation are retained unchanged.
