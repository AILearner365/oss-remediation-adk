# Product contract — Autonomous OSS Vulnerability Remediation

Status: **partial implementation; native preparation migration BLOCKED** on the
inspected OpenHands 1.55.1 installation. OpenHands is the implementation framework,
not the product identity. Preserved diagnostics at `11431b428a69f4525679bda5880bf0a0d05137bc`
do not yet satisfy the mandatory native-owned preparation contract below.
The verified Milestone 1 smoke remains at `f72e5308704960ee911f382f96bf0b7948435216`.
See [source evidence and exact blocker](docs/NATIVE-PREPARATION-BLOCKER.md).

## Outcome and operating model

Given an approved repository revision and a remediation objective, autonomously investigate, select and implement a credible solution, independently verify it, and deliver *only a verified result* as a GitHub draft PR. If the goal cannot be met within policy/budget, return an evidence-backed bounded failure, not a fictional success. The general operating model is technology-neutral; Java Maven OSS remediation is the first application.

**Lifecycle**: stable task/constraints -> read-only discovery -> facts, uncertainty and assumptions -> success criteria -> credible candidates covering the *whole* goal -> chosen strategy (cycle intent) -> investigation/implementation -> reassessment and agent self-checks -> cycle outcome -> independent deterministic validation -> succeed or next bounded cycle -> final resolution -> safe delivery.

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

Native OpenHands Agent Server/SDK handles conversations, agent execution, supported tools and hook invocation; Canvas is optional native observation, not a separate product UI. Model used in proven smoke: `vertex_ai/gemini-2.5-flash` with Vertex AI. Configuration must be explicit and replaceable. Native version proven: SDK/Server/tools 1.55.1, Canvas 1.27.1. Verify extension contracts against installed code before implementing.

Minimal integration responsibilities:
1. **Preparation/submit**: native conversation/workflow initialization must own
   trusted deterministic workspace preparation and baseline, with an explicit
   COMPLETE prerequisite before any inference. It receives repo/ref + approved
   SHA, goal, constraints, acceptance policy, limits and authorized destination.
   Effective hooks must be resolved before running (1.55.1 initializes hooks on
   the first `run:false` message). The preserved external prepare/attach/run
   diagnostics are not an implementation of this native ownership requirement.
2. **Agent capabilities**: grant needed repository, shell, Maven, OSV/scanner, research and optionally SBRI/release-intelligence access with bounded permissions. Reuse/copy/rework experimental code freely; agent selects when to use capabilities. SBRI is a helper, not an obligatory Spring Boot strategy; current test scanner is OSV, production candidate JFrog Xray requires a separate adapter/verification.
3. **Independent validation**: apply task-specific acceptance contract to an immutable captured candidate Git tree and baseline. Check actual resolved dependency set and findings, remaining/new vulnerabilities, applicable upgrade policy, Maven build/tests and repository constraints. Explicitly distinguish scanner errors, incomplete coverage and unknowns from PASS. Ensure paths/dependency source are available as required. Record attempt evidence and provide actionable failure context through native Stop Hook; accepted completion requires proof for the exact conversation, approved base and validated tree.
4. **Delivery**: after independent PASS only, bind output to the validated Git tree, verify remote base/destination, create-only branch/commit, and confirm an open **draft** PR identity. Preserve local claims and reconciliation; ambiguous remote mutation must block, not duplicate blindly. Fail closed at the product acceptance level even if native hook-command failures can fail open.
5. **Recovery/evidence**: use native conversation/events plus small durable task/intent/outcome/validation/delivery artifacts as needed, without reimplementing native history, task API, UI or lifecycle database. Keep secrets out of workspaces and committed artifacts. Avoid unrestricted retries.

### Mandatory pre-inference guarantees

Normal product execution must establish all of these through supported native
extensions: (A) preparation inside the conversation lifecycle, (B) completion
before any Gemini inference, (C) failure prevents inference, (D) evidence bound
to that conversation, (E) recovery cannot silently skip/duplicate preparation,
and (F) preparation authority isolated from agent-controlled content/commands.
Preparation is deterministic code, never an agent-selected reasoning step.
Untrusted Maven build logic must not gain trusted evidence/credential authority.

The inspected installation does not provide a verified mechanism satisfying all
six. SessionStart is not a blocking gate; UserPromptSubmit denial is consumed,
and hook infrastructure errors can fail open. Remote `execute_tool()` is
unsupported. Native bash execution has no enforced dependency on subsequent
`/run`. Current hook/build processes do not establish separate OS trust domains.
The migration is stopped; no wrapper, patched SDK or custom orchestrator is an
acceptable substitute. Existing validator/delivery code remains available for
diagnostic verification, not certified normal product execution.

## Inputs and outputs

Minimal task input: repository and approved base (branch + immutable SHA), remediation goal, acceptance policy/constraints, resource/time limits, authorized PR destination, tool/credential references (never credentials in agent prompt). Baseline may be generated as deterministic preparation; do not force user-supplied CVE lists as the only workflow.

Output: deterministic baseline; per-cycle facts/assumptions, candidate rationale and intent/outcome; actual resolved dependencies and scanner coverage; changed files and immutable Git tree; independent PASS/FAIL/INCONCLUSIVE per attempt with reasons; final summary; verified PR URL **or** bounded failure/blocked result. Keep interfaces straightforward, documented and adjustable; avoid speculative DSLs or large schemas.

## Proven versus unproven

**PROVEN in native one-file smoke:** native conversation and Gemini execution, one Stop Hook invocation, exact one-file deterministic PASS, validated tree/base binding, successful draft PR #214, native/API visibility; no custom product API/UI/SQLite needed. Reference: `docs/experiments/openhands/OPENHANDS-NATIVE-WIRING-SMOKE.md` at parent commit.

**NOT PROVEN by smoke:** Maven/OSV validator under native Stop Hook; full goal remediation; cycles/denials on this adapter; agent reasoning quality; policy/scanner coverage; production durability/recovery; Canvas browser activity; secure production multi-user isolation. Earlier experiments support design but are not equivalent to production proof.

Known limitations to address proportionately: temporary Cloud Shell ADC discovery workaround; local-only claim persistence; native command hook may fail open on process failure; shared OS user between agent and hook; old one-file submitter's 3-iteration/terminal-only/no-retry restrictions and hook exact-file whitelist are *smoke-specific*, not product defaults.

## Implementation discipline

Build a **clean tree**, copying only purposeful code from parent/history. Follow the conventions of installed OpenHands, but do not prematurely prescribe packages/files; choose the minimum cohesive set with tests. No custom server, UI, SQLite, lifecycle coordinator, second agent or competing orchestration engine unless a truly missing capability is demonstrated. No gratuitous abstraction, recipes, forced alternatives or unrelated refactors. "Low footprint" is a result of clear responsibilities, not an arbitrary line-count goal.

Engineering has discretion over internal file layout and adapters. It must show concrete mapping from this contract to code and tests, and a short proof table (PROVEN/PARTIAL/NOT PROVEN). Do not declare success on unit tests alone. Security-sensitive operations must be checked before externally creating PRs or running model calls.

## Immediate execution boundary

Only code/documentation changes, focused offline checks and read-only native
capability inspection are authorized for this correction. No Gemini call,
runtime install/upgrade, target-repo edit, delivery PR or remediation run is
authorized. Product development is on `autonomous-oss-remediation`; the original
`openhands-native-product` branch and its implementation are retained unchanged.
