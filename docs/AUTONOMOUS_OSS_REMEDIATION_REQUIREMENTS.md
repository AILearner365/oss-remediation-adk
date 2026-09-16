# Autonomous OSS Remediation Agent — Requirements and Implementation Review

## 1. Purpose

This document defines the requirements for a new autonomous OSS vulnerability remediation agent implemented alongside the existing `oss_remediation_agent`.

The existing implementation is reference material only. The new implementation must be independently runnable and must not import or depend on implementation code from `oss_remediation_agent`.

The purpose of the experiment is to compare the existing highly prescribed planner/patch workflow with a tool-enabled autonomous coding-agent approach.

**Core design rule:**

> AI controls **how** to solve the engineering problem. Deterministic code controls **where** it may operate, **what** constraints it must respect, **whether** the result actually passes validation, and **whether** it is eligible for PR delivery.

A second design principle applies to the developer-tool layer:

> Define the capabilities the autonomous agent needs and the boundaries it must respect. Do not preselect the implementation mechanism before the available options have been investigated.

Examples discussed during design conversations — such as ADK-native tools, custom Python function tools, local tool providers, MCP servers, GitHub integrations, or other trusted vendor integrations — are **examples for investigation, not architectural preferences or mandatory choices**.

---

## 2. Existing Implementation as Reference

Before designing or implementing the new agent, inspect the existing `oss_remediation_agent` and understand how it currently handles:

- Google ADK setup and execution
- repository/workspace preparation
- Git clone and branch handling
- Maven baseline build
- Spring Boot startup/build validation where applicable
- OSV Scanner execution
- OSV result parsing and normalization
- severity filtering
- policy/user constraints
- validation
- Git operations
- branch/commit/push
- Draft PR creation
- configuration/environment handling
- artifacts/results used for traceability

Useful behavior may be copied, adapted, or independently reimplemented under the new package. Do not create runtime imports/dependencies from the new agent to `oss_remediation_agent`.

Do not modify the existing agent unless a repository-level configuration change is genuinely required. Explain such a requirement before changing it.

---

## 3. New Package

Create an independent package, for example:

```text
autonomous_oss_remediation_agent/
```

The exact internal structure should be proposed during design review rather than prescribed here.

---

## 4. Architecture

Keep the initial architecture intentionally simple:

```text
User Request
     |
     v
1. Repository Preparation       deterministic
     |
     v
2. Baseline / Assessment        deterministic
     |
     v
3. Autonomous Remediation       one primary LLM agent + developer capabilities
     |
     v
4. Independent Validation       deterministic
     |
     +---- FAIL ----> same autonomous agent continues
     |
     +---- PASS ----> 5. Delivery
                       deterministic Git / Draft PR
```

Do not recreate the existing many-agent pipeline for the initial POC.

Prefer **one primary autonomous LLM remediation agent**. Repository preparation, scanning, objective validation, execution boundaries, and delivery should remain deterministic where practical.

---

## 5. User Inputs / Remediation Contract

Support inputs such as:

- repository URL
- reference branch
- workspace location when applicable
- vulnerability severities/findings to remediate
- user constraints
- build/test expectations
- remediation execution budget

Examples of constraints include:

- do not upgrade Java
- do not upgrade Spring Boot
- do not suppress vulnerabilities
- do not introduce new HIGH/CRITICAL vulnerabilities

These inputs define the objective and guardrails. They must not become hard-coded instructions for how dependencies should be remediated.

---

## 6. Stage 1 — Repository Preparation

Repository preparation should be deterministic.

Responsibilities:

- create an isolated workspace
- clone the requested repository/reference branch
- prepare working Git state
- record relevant initial metadata
- establish information required for later constraint verification

Study the existing implementation and independently reproduce useful clone/workspace/Git behavior.

---

## 7. Stage 2 — Baseline and Vulnerability Assessment

Before autonomous changes begin:

1. establish the repository baseline
2. execute the appropriate Maven baseline build
3. execute OSV Scanner using the already-working project integration/pattern where appropriate
4. parse and normalize scanner findings
5. identify findings matching requested remediation scope
6. record project information needed for later constraint validation

Scanner evidence, not an LLM opinion, determines the vulnerability baseline.

Where possible, independently adapt the proven OSV execution/parsing approach from the existing implementation instead of inventing a new scanner integration.

---

## 8. Stage 3 — Autonomous Remediation Agent

Implement one capable Google ADK LLM agent responsible for investigating and remediating the requested OSS vulnerabilities directly in the prepared repository while respecting all supplied constraints.

The agent should receive:

- workspace/repository context
- baseline vulnerability findings
- requested remediation scope
- user constraints
- completion criteria
- available developer capabilities/tools
- validation feedback from previous attempts

### 8.1 Engineering freedom

The autonomous agent should be free to determine, based on repository evidence:

- Maven project/module structure
- direct vs transitive dependency relationships
- dependency-management ownership
- parent POM/BOM influence
- framework-managed versions
- effective dependency versions
- compatibility implications
- appropriate Maven commands
- appropriate repository searches
- appropriate files to modify
- whether a Maven plugin could help
- whether a temporary script/tool would help
- how to react to compilation/test/build failures
- whether an attempted approach should be revised or reverted

These are examples of possible reasoning, not mandatory workflow steps.

### 8.2 No rigid patch-plan interpreter

Do not require a rigid machine-readable remediation plan that deterministic application code must interpret before changes can be made.

The desired model is:

```text
problem -> investigate -> modify -> execute -> observe -> adapt -> verify
```

not:

```text
problem -> structured patch plan -> patch interpreter -> predefined remediation implementation
```

### 8.3 Behavioral principles

The autonomous agent should:

1. understand evidence before modifying the project
2. investigate how affected dependencies are actually introduced and managed
3. respect existing dependency-management conventions where reasonable
4. make justified compatible changes rather than blindly optimizing for the smallest textual diff
5. use repository/build evidence rather than assumptions
6. execute commands/tools as needed to test hypotheses
7. inspect failures and adapt
8. not declare success merely because a file changed or a build passed
9. continue until objective completion criteria pass or execution budget is exhausted
10. clearly report when remediation cannot be achieved without violating supplied constraints

Do not encode vulnerability-specific remediation recipes into the prompt.

---

## 9. Developer Capabilities and Tooling Selection

The requirement is **capability-based**, not tool-implementation-based.

The autonomous agent needs sufficient developer capabilities to investigate and remediate a real repository. At minimum, the selected approach must enable the equivalent of:

### Repository/workspace investigation and modification

- discover files/directories and project structure
- read files
- search files/content
- create files when useful
- edit or patch files safely
- inspect resulting changes/diffs

### Developer execution and observation

- execute the build/test/dependency-analysis commands needed for the repository
- use available developer binaries and project tooling where appropriate
- capture stdout, stderr, exit status, timeout/failure information, and enough output for diagnosis
- create and execute workspace-local scripts or temporary helpers when appropriate
- observe failures and continue iterating

### Repository and integration operations where applicable

- inspect Git state/history needed for engineering work
- obtain dependency/build/security evidence needed to reason about remediation
- interact with approved external services only when the design determines that such access is useful and appropriately bounded

Before implementation, inspect the actual Google ADK version, repository environment, installed/available tools, and approved integrations. Investigate reasonable implementation options and propose the approach that best supports autonomous remediation while remaining maintainable and appropriately bounded.

Possible mechanisms may include ADK-provided capabilities, callable/custom tools, local tool providers, trusted vendor integrations, MCP-based integrations, command execution, or combinations of these. **This list is illustrative only. It does not express a preference and does not require every category to be evaluated when it is irrelevant.**

Do not create separate Maven/Java/Python/Git abstractions merely because they are easy to enumerate. Likewise, do not force all capabilities through one general terminal tool if a different approach is clearly better. The design should choose the smallest coherent capability set that gives the agent enough freedom to work effectively.

The selected tooling should not unnecessarily constrain the agent's ability to inspect, modify, build, test, scan, observe failures, and adapt.

---

## 10. Tool, Plugin, and Integration Flexibility

Within the approved execution boundary, the autonomous agent may:

- invoke Maven plugins
- create temporary scripts
- use existing developer tools
- use lightweight project/workspace-scoped tools when useful
- inspect generated dependency/build information
- perform iterative engineering experiments
- use approved local or trusted-provider integrations when they materially improve the workflow

Do not preselect OpenRewrite, versions-maven-plugin, MCP, a filesystem provider, a GitHub provider, or any other implementation mechanism as mandatory. Equally, do not exclude such a mechanism solely because of its category. The design should justify the actual choice based on capability, safety, maintainability, environment support, and usefulness to this POC.

Trusted/vendor-supported integrations may be considered where appropriate. Arbitrary or untrusted third-party integrations should not be introduced casually into the remediation runtime.

The agent must not autonomously:

- use `sudo`
- modify system-wide security configuration
- alter credentials
- globally replace the machine JDK
- modify unrelated repositories/directories without an explicit justified requirement
- modify Jenkins/system configuration
- install arbitrary system services/daemons
- make unrestricted machine-wide changes

The exact filesystem, command, network, GitHub, and integration boundaries are a **design decision to be proposed and reviewed**, not predetermined here beyond these safety principles.

If runtime installation is supported, prefer temporary/project-scoped installation unless the approved design clearly requires otherwise.

---

## 11. Stage 4 — Independent Deterministic Validation

The autonomous agent does not decide whether remediation succeeded.

After each work cycle, independently validate at minimum:

- required Maven build succeeds
- required tests/validation succeed
- a fresh OSV scan executes successfully
- requested target vulnerabilities/severities are resolved according to scope
- no prohibited new vulnerabilities are introduced
- user constraints remain satisfied
- protected versions such as Java/Spring Boot remain unchanged when explicitly constrained
- prohibited suppression/ignore mechanisms were not introduced when disallowed
- resulting Git diff is available for review

Validation results must be represented in structured form and be suitable for feeding back to the autonomous agent.

---

## 12. Autonomous Feedback Loop

Do not recreate the existing plan -> patch interpreter -> outcome-analysis agent -> replanning-agent sequence.

Use:

```text
Autonomous agent works
        |
        v
Deterministic validation
    /          \
 PASS          FAIL
  |             |
Delivery    validation evidence
                |
                v
        SAME autonomous agent
           continues work
```

On failure, provide concrete evidence such as:

- Maven compilation/test errors
- remaining vulnerability findings
- constraint violations
- relevant validation diagnostics

The same workspace should normally be retained so the agent can continue investigating rather than restarting every attempt.

Support configurable execution/resource boundaries such as:

- maximum remediation/validation cycles
- command/tool timeout where applicable
- overall reasonable execution budget

These are resource/safety limits, not predefined remediation strategies.

---

## 13. Stage 5 — Delivery

Successful automated delivery is permitted only after deterministic validation passes.

Then perform deterministic Git/PR operations such as:

- inspect final diff
- create/use remediation branch
- commit
- push
- create Draft PR

Study and independently adapt useful Git/PR patterns from the existing implementation. The implementation may use an appropriate approved Git/GitHub mechanism; this requirements document does not prescribe CLI, API, MCP, or another integration.

The LLM may generate the PR explanation, including vulnerabilities addressed, dependency changes, rationale, validation performed, and validation results. Git mechanics and the decision that remediation passed remain deterministic.

---

## 14. Traceability

Capture enough evidence to understand the run without reproducing unnecessary workflow complexity:

- baseline scan
- baseline build
- relevant command/tool actions
- files changed
- validation cycles
- validation failures
- final scan
- final build
- constraint checks
- final status
- PR information

Avoid elaborate schemas/manifests unless they provide clear value for this POC.

---

## 15. Final Outcomes

Support clear outcomes:

### SUCCESS
Objective validation passed and Draft PR was created.

### PARTIAL / MANUAL REVIEW REQUIRED
Some remediation was achieved but completion criteria remain unsatisfied.

### NO SAFE REMEDIATION
Available approaches would violate supplied constraints, or no compatible remediation could be established from available evidence.

### EXECUTION LIMIT REACHED
The autonomous work/validation budget was exhausted.

### BASELINE FAILURE
Repository/build/scanner baseline prevented remediation from safely beginning.

Never fabricate successful remediation.

---

## 16. Explicit Non-Goals for Initial POC

Do not introduce unless an unavoidable technical requirement is discovered and justified:

- OpenHands
- SWE-agent
- LangChain
- vector databases
- long-term learning/memory
- multiple specialist remediation agents
- vulnerability-specific hard-coded strategies
- a large general-purpose tool platform that is not needed for the POC

The goal is a focused autonomous-remediation POC, not commitment to or rejection of a particular tool protocol.

---

# 17. Mandatory Design Review Gate — Before Implementation

**Do not begin implementation immediately.**

First inspect the repository and produce or revise a design proposal for review.

The proposal must cover the following checklist. Mark each item only after it has actually been investigated.

### Existing system and environment

- [x] Existing `oss_remediation_agent` architecture reviewed
- [x] Existing repository/workspace/clone implementation reviewed
- [x] Existing Maven build/startup implementation reviewed
- [x] Existing OSV execution and parsing implementation reviewed
- [x] Existing policy/constraint handling reviewed
- [x] Existing Git/branch/commit/push/PR implementation reviewed
- [x] Existing tests and demo scenarios reviewed
- [x] Current Google ADK version/dependencies identified

### Developer capability design

- [x] Required autonomous developer capabilities identified from the remediation objective
- [x] Relevant implementation/integration options available in the actual environment investigated
- [x] Proposed capability/tool/integration approach documented with rationale
- [x] Proposed approach shown in design to cover repository inspection, modification, execution, build/test/scan, and iterative diagnosis; runtime demonstration remains an implementation verification item
- [x] Permissions, security boundaries, credentials, network behavior, and operational limitations documented
- [x] Tooling choices reviewed for unnecessary restrictions on autonomous engineering behavior
- [x] Trusted/local/vendor integrations considered where relevant without treating any example as mandatory

### Autonomous lifecycle and verification

- [x] Autonomous remediation execution loop documented
- [x] Deterministic validation boundary documented
- [x] Validation-failure feedback loop documented
- [x] Execution-budget/termination behavior documented
- [x] Proposed independent package/file structure documented
- [x] Code that will be copied/adapted conceptually from existing implementation identified
- [x] Runtime dependencies on existing `oss_remediation_agent` confirmed as NONE
- [x] Important ADK limitations/technical uncertainties documented
- [x] Focused testing strategy documented

The design proposal should explicitly explain:

1. what remains deterministic
2. what is delegated to the autonomous LLM
3. what developer capabilities the LLM receives and the chosen implementation/integration approach
4. why that approach was selected over materially relevant alternatives
5. how permissions and operational boundaries are enforced without unnecessarily reducing autonomy
6. how the LLM continues working after validation failure
7. how success is independently established
8. how the implementation remains independent from the existing agent

**STOP after producing or revising the proposal. Do not modify implementation files until the proposal has been reviewed/approved.**

---

# 18. Implementation Checklist — After Design Approval

Once the design proposal is approved, implement against this checklist. Keep this document updated as work progresses, but do not mark an item complete merely because code exists; mark it complete only when implementation and relevant verification are present.

## Independent implementation

- [ ] New autonomous package created
- [ ] Existing `oss_remediation_agent` remains functionally unchanged
- [ ] New implementation has no runtime imports from existing agent
- [ ] Independent configuration/entry point exists

## Preparation and baseline

- [ ] Isolated workspace creation implemented
- [ ] Repository clone/reference branch handling implemented
- [ ] Baseline Maven build implemented
- [ ] Baseline OSV scan implemented
- [ ] OSV parsing/normalization implemented
- [ ] Requested severity/finding scope implemented
- [ ] Constraint baseline captured

## Autonomous engineering agent

- [ ] One primary ADK remediation LLM agent implemented
- [ ] Repository inspection/reading capability available
- [ ] Repository search/discovery capability available
- [ ] File creation/editing/patch capability available
- [ ] Required developer command/execution capability available
- [ ] stdout/stderr/exit/failure evidence available where applicable
- [ ] Timeout/resource boundaries enforced where applicable
- [ ] Approved workspace/integration boundaries enforced
- [ ] Tool/plugin/integration flexibility supported within policy
- [ ] No rigid patch-plan interpreter required
- [ ] No vulnerability-specific remediation strategy hard-coded
- [ ] Selected tool/integration mechanism matches the approved design rather than an unreviewed assumption

## Validation and iteration

- [ ] Independent Maven build/test validation implemented
- [ ] Independent fresh OSV rescan implemented
- [ ] Target finding resolution comparison implemented
- [ ] New prohibited vulnerability detection implemented
- [ ] User constraint validation implemented
- [ ] Suppression/ignore policy validation implemented where applicable
- [ ] Git diff captured/reviewable
- [ ] Structured validation feedback implemented
- [ ] Failed validation returns evidence to the same autonomous agent/workspace
- [ ] Maximum remediation/validation cycles enforced
- [ ] Command/tool/runtime budget behavior implemented
- [ ] Truthful incomplete/manual-review outcome implemented

## Delivery

- [ ] Delivery gated on deterministic validation success
- [ ] Remediation branch handling implemented
- [ ] Commit implemented
- [ ] Push implemented
- [ ] Draft PR creation implemented
- [ ] PR summary includes remediation and validation evidence

## Traceability and tests

- [ ] Baseline evidence retained
- [ ] Relevant tool/command actions traceable
- [ ] Validation cycles traceable
- [ ] Final build/scan/constraint evidence retained
- [ ] Unit/focused tests added
- [ ] Workspace/integration boundary behavior tested
- [ ] Validation failure feedback loop tested
- [ ] Execution budget exhaustion tested
- [ ] Delivery gating tested
- [ ] End-to-end vulnerable Maven/Spring demo smoke test performed where practical

---

# 19. Mandatory Post-Implementation Self-Review

After implementation, perform a fresh review of the implementation against this requirements document.

Do not merely report that implementation is complete.

For every checklist item above:

1. verify it against actual code/tests/runtime evidence
2. mark `[x]` only when supported by evidence
3. leave incomplete items as `[ ]`
4. add a short note for incomplete or intentionally deferred items
5. identify deviations from the approved design
6. identify any new hard-coded remediation behavior that accidentally reduced autonomy
7. identify any place where the LLM is trusted to declare success instead of deterministic validation
8. identify any tool/integration capability that exceeds the approved boundary
9. identify any tool/integration choice that unnecessarily reduced the agent's useful engineering autonomy
10. run the relevant tests
11. summarize remaining gaps before declaring the POC complete

The final review should answer:

- Is the implementation truly independent from the existing agent?
- Is there one primary autonomous engineering agent rather than another prescribed multi-agent remediation pipeline?
- Can the agent inspect, modify, execute, observe failures, and adapt?
- Does deterministic validation, rather than LLM opinion, decide success?
- Does failed validation feed concrete evidence back into continued autonomous work?
- Are user constraints enforced independently?
- Is PR delivery impossible until validation passes?
- Are execution/tool/integration boundaries appropriately constrained without being unnecessarily restrictive?
- Did the implementation avoid embedding detailed Maven vulnerability remediation recipes?
- Was the selected developer-tool approach justified by the actual environment rather than by examples mentioned in requirements discussions?

**The POC is not considered complete merely because all boxes were manually checked. Checklist status must reflect actual implementation and verification evidence.**
