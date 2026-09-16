# Autonomous OSS Remediation Agent — Design Review and Required Revision

**Status:** Review complete. The overall architecture is accepted as the working direction, but the developer-tool portion of the proposal must be revised before implementation is approved.

**Reviewed proposal:** `docs/AUTONOMOUS_OSS_REMEDIATION_DESIGN_PROPOSAL.md` from commit `219bd2f485f64c6e9112ee2f9df58258c26b2853`.

**Authoritative requirements:** `docs/AUTONOMOUS_OSS_REMEDIATION_REQUIREMENTS.md` as updated after this proposal was produced.

## 1. What remains valid from the proposal

The following design decisions remain aligned with the experiment and should be retained unless new evidence shows a concrete problem:

- one primary Google ADK remediation LLM agent rather than a prescribed multi-agent remediation pipeline;
- deterministic repository preparation and baseline establishment;
- deterministic vulnerability evidence and normalization;
- the autonomous agent directly investigates and changes the working repository instead of emitting a rigid patch plan for Python to interpret;
- the same agent/session and working repository continue after failed validation;
- deterministic validation, not the LLM's statement, decides whether remediation succeeded;
- deterministic delivery remains gated on validation success;
- no runtime dependency from the new package to `oss_remediation_agent`;
- bounded execution/resource limits and traceability;
- no vulnerability-specific remediation recipes embedded in the agent prompt.

The core flow remains:

```text
prepare -> baseline -> autonomous engineering -> deterministic validation
                                      ^                 |
                                      |------ FAIL -----|
                                                        |
                                                     PASS
                                                        |
                                                   delivery
```

## 2. Main issue found in the current proposal

The proposal correctly investigated the locally installed ADK environment, but it moved too quickly from those observations to one specific developer-tool implementation.

In particular, the current proposal:

- concludes that a custom callable/function-tool layer should be used;
- fixes the LLM toolset to exactly six tools;
- fixes exact file-tool semantics and command-runner semantics;
- fixes a `shell=False`/argument-vector execution model;
- fixes repository-root-only behavior and a detailed executable/network allow/deny policy;
- treats the stock ADK environment toolset as rejected rather than one investigated option;
- does not materially investigate other potentially suitable local or trusted integration mechanisms before selecting the custom layer.

Those choices may ultimately be correct, but they should be **design conclusions supported by comparison**, not assumptions inherited from the requirements.

The requirements have therefore been revised so that developer tooling is capability-driven rather than implementation-driven.

## 3. Updated design principle for tools

The design must start from the capabilities required by autonomous remediation:

- discover and understand repository structure;
- read/search project content;
- safely modify project content;
- run the developer/build/dependency commands required by the repository;
- observe stdout/stderr/status/timeouts and continue after failures;
- use project-local scripts/plugins/helpers where useful;
- inspect Git state/diffs needed for engineering work;
- consume security/build evidence;
- interact with approved external or vendor services when that materially improves the workflow;
- remain within reviewed operational and security boundaries.

The implementation mechanism is a design choice.

Examples that may be relevant include ADK-provided tools, callable/custom Python tools, local providers, trusted vendor integrations, MCP-based integrations, command execution, or combinations of these. These are **examples, not preferences**. The revised design does not need to compare every category; it should investigate only materially relevant options available in the actual environment.

## 4. Required revision to the existing proposal

The next design revision should preserve the strong architecture above but reopen the following parts of the current proposal.

### A. Installed ADK/tool capability conclusion

Keep the factual investigation of the installed ADK version and the observed limitations of `LocalEnvironment`, `EnvironmentToolset`, `ExecuteBashTool`, etc.

Change the conclusion from:

> therefore use a custom callable/function-tool layer

to:

> these findings eliminate or weaken some options, but the final developer-capability implementation should be selected after materially relevant available options are investigated and compared.

### B. "Exact Agent Toolset"

Do not treat the current six-tool list as approved architecture.

The six custom tools can remain a **candidate design** if they are still judged best after investigation. The revised proposal should explain:

- what capabilities are actually required;
- which implementation options were materially available;
- what option or combination was selected;
- why it was selected;
- what useful autonomy would be lost or gained compared with alternatives;
- what extra dependency/complexity the choice introduces.

The final implementation may still expose six custom tools, fewer broader tools, trusted provider tools, an MCP-backed capability, or a hybrid. The requirements do not predetermine that answer.

### C. Tool boundaries and permissions

The current path, shell, executable, network, GitHub, and credential controls should be treated as **proposed controls**, not requirements that must survive unchanged.

The revised proposal should distinguish:

1. hard safety/objective boundaries that should remain regardless of implementation;
2. controls required by a particular tool implementation;
3. restrictions that may unnecessarily reduce the coding agent's engineering capability.

For example, restricting unrelated machine-wide changes is a stable safety objective. Whether the correct technical implementation is repository-root path guards, a sandbox/container, provider-level filesystem scoping, an MCP server root, command policy, or another mechanism is a design choice.

### D. Git/GitHub and external integration

Deterministic PR delivery remains the required boundary, but the mechanism for Git/GitHub operations is not prescribed.

The revised proposal should investigate the appropriate available method for the environment instead of assuming `gh` or assuming that GitHub capabilities must never be exposed to the remediation agent. The important distinction is authority:

- engineering inspection/context may be useful to the LLM when justified;
- the determination that validation passed remains deterministic;
- final commit/push/PR delivery remains policy-gated and deterministic unless the requirements are explicitly changed later.

### E. Package structure

The proposed independent package structure remains a useful candidate, but tool-specific filenames such as `developer_tools.py` / `command_runner.py` should not force the architecture before the tool approach is selected.

The revised proposal may retain them if the selected design genuinely uses that structure.

## 5. Design-review checklist reopened by this change

The tooling-related portion of the design gate is intentionally reopened. It is not a failure of the original investigation; the requirements themselves changed after the proposal was produced.

The revised proposal must establish:

- [ ] Required autonomous developer capabilities identified from the remediation objective
- [ ] Materially relevant implementation/integration options available in the actual environment investigated
- [ ] Selected capability/tool/integration approach documented with rationale
- [ ] Selected approach shown to support repository inspection, modification, execution, build/test/scan, and iterative diagnosis
- [ ] Permissions, security boundaries, credentials, network behavior, and operational limitations documented
- [ ] Tooling choices reviewed for unnecessary restrictions on autonomous engineering behavior
- [ ] Trusted/local/vendor integrations considered where relevant without treating any example as mandatory

Do not mark an item complete merely because the original proposal already discussed custom tools. Re-evaluate it against the revised requirements.

## 6. What should NOT be reopened unnecessarily

This tooling revision should not turn into a redesign of the entire POC.

Unless investigation finds a concrete technical reason, do not reopen:

- one primary remediation agent;
- deterministic baseline/scanning;
- direct autonomous modification instead of a patch-plan interpreter;
- same-session validation feedback loop;
- deterministic success validation;
- deterministic delivery gate;
- independent package requirement;
- bounded execution and truthful incomplete outcomes.

The goal is to correct premature tool selection while preserving the simple architecture already proposed.

## 7. Instruction for the next Codex design pass

Read the updated `docs/AUTONOMOUS_OSS_REMEDIATION_REQUIREMENTS.md`, this review, and the existing design proposal.

Revise `docs/AUTONOMOUS_OSS_REMEDIATION_DESIGN_PROPOSAL.md` so it remains one coherent proposal rather than creating a second competing architecture.

Preserve the parts of the existing proposal that still satisfy the requirements. Re-investigate and revise only the areas affected by the capability-driven tooling update, especially the current Sections 3, 7, 8, 14, and 17 and any checklist statements that depend on them.

Do not interpret examples mentioned in the requirements or this review as preferred technologies. Investigate what is actually available and appropriate in the current project/environment.

After revising the proposal:

1. update the design-review checklist in the requirements document only where the new investigation provides evidence;
2. summarize what changed from the original proposal and why;
3. identify any unresolved design decisions;
4. stop before implementation.

**Implementation remains blocked until the revised proposal is reviewed and explicitly approved.**
