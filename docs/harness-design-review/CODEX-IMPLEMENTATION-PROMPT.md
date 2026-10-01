# Codex implementation prompt — harness responsibility boundaries

Work in AILearner365/oss-remediation-adk on branch context-hygiene-clone-challenge-before-commitment.

Read docs/project-memory/START-NEW-CHAT.md and follow its continuity procedure. Read docs/harness-design-review/REVIEW-NOTES.md. Reconcile both with the actual branch head, applicable AGENTS.md instructions, active package code, tests and saved traces. The active implementation is autonomous_oss_remediation_agent; older packages are historical.

## Objective

Implement a coherent simplification of the harness/model responsibility boundary. The model owns investigation, engineering judgment, strategy selection, implementation, reassessment and self-validation. The harness owns execution mechanics, permissions, lifecycle state, bounded recovery, evidence retention and audit rendering.

The concern is that wrappers impose bookkeeping, exact formatting and repair work without demonstrated improvement in engineering decisions. Do not respond by adding more reasoning instructions, a new agent, or another general remediation benchmark. Use established harness practices to correct concrete interface/reliability defects. Do not replace the framework or rebuild working enterprise adapters.

## Reconcile before editing

The original review covered d931c3fcaf79d6c8e4a48b8db88651a06714f3d1. At prompt preparation, head was 1d04423202c8a62cddfbc6a3a7c3070b98b47ed9. Its code adds Intent-phase unknown-tool correction, a shared bounded checkpoint allowance, improved size feedback and per-session interaction-artifact names. Verify those changes and any newer commits; do not reimplement them or assume they establish complete recovery or live acceptance.

Briefly record: already fixed; remaining defect or responsibility mismatch; smallest coherent change; focused verification. Inspect model-visible ADK declarations, actual responses and exception handling, not just Python method signatures. Then proceed with implementation; do not stop at an assessment or ask for routine reconfirmation.

## Implementation scope

1. Simplify Intent and Outcome capture.
   - Preserve meaningful pre-execution decision information, substantive answers and retrospective Outcome coverage. Preserve the existing reasoning objectives, including evidence-backed selection and challenge before commitment.
   - Replace brittle exact Markdown tables/headings/labels inside JSON with a compact typed contract. Choose the smallest schema that preserves necessary information; do not translate every prose rule into another required field.
   - Generate the readable journal in deterministic code. Derive observable action chronology from events; never fabricate model rationale or evidence.
   - Give precise field-level errors and permit localized correction without repeatedly regenerating valid content. Prevent cross-cycle leakage, stale partial submissions and premature acceptance; reject incomplete or invalid checkpoints atomically.
   - Update tool declarations, validation, prompt submission guidance, rendering and tests together. Document schema migration and keep historical traces readable. Do not weaken content requirements merely to pass capture.

2. Align capabilities and recovery.
   - Review the new callback for phase and tool assumptions. Recovery should reflect actual registered/available capabilities; do not redirect every unknown call to Intent simply because it occurred before Intent.
   - Where supported safely by the pinned ADK version, align model-visible capabilities with phase availability. Keep server-side enforcement regardless; avoid fragile framework overrides solely for dynamic exposure.
   - Recover from malformed/unknown invocations within the same session and cycle when protocol integrity permits. Return explicit bounded feedback, execute no invented alias, and retain run budgets. Distinguish invocation errors from execution, provider, session and infrastructure failures.
   - Preserve the model's investigate -> implement -> observe -> reassess -> revise -> self-validate loop. Do not replace it with repeated fresh model attempts or advance cycles for ordinary recoverable errors.

3. Preserve durable evidence and continuity.
   - Verify the per-session artifact fix rather than replacing it unnecessarily. Ensure events and payloads remain uniquely addressable across recreated sessions.
   - Make material evidence retrievable after session replacement, including evidence obtained before an unsuccessful checkpoint. Supply concise supported state and references rather than blindly replaying all history or treating old conclusions as authoritative.
   - Keep summaries, source evidence and deterministic validation distinguishable. Retain authorization checks on evidence retrieval.

4. Make approved evidence usable.
   - Preserve company-required GitHub, OSV/JFrog Xray, proxy, TLS/certificate, authentication and network arrangements. Do not change scanner selection, scanner policy or delivery semantics.
   - Review source acquisition separately from extraction and model-facing formatting. Address demonstrated format restrictions such as rejection of an authorized Maven POM as text/xml through general source-format handling, not Maven-specific strategy logic.
   - Distinguish acquisition failure, extraction failure, source truncation and bounded display. Preserve authorized raw evidence and provenance with useful bounded views and retrieval where applicable.
   - Do not bypass approved network restrictions, disable TLS verification, introduce an unapproved search provider or report unavailable evidence as an empty successful result.

## Verification and reporting

Use focused contract and ADK-boundary tests for valid capture, localized malformed-input repair, phase enforcement, bounded unknown-tool recovery, oversized input feedback, no authoritative mutation before accepted Intent, same-cycle continuation, session recreation, artifact preservation, retained-evidence retrieval, and supported/unsupported research content formats. Use realistic controlled fixtures; do not rely solely on scripted sessions that bypass the relevant boundary. Run the relevant regression suite and diff checks.

Do all useful implementation and offline verification even if this machine cannot run live models or real scanners. Do not start paid/live runs or general remediation batches for this task. State precisely what remains unverified live; a new quality comparison is not a prerequisite for these repairs.

Update affected authoritative design/API documentation and PROJECT-DIRECTION.md, WORK-STATE.md and DECISION-LOG.md. Record the new immediate work and preserve outstanding live-evidence questions. Treat this request as superseding the older instruction to perform a live batch before interface cleanup. Keep these development documents out of runtime context. Preserve Q1–Q5 reasoning semantics while changing serialization and duplicated submission instructions as necessary; record such changes explicitly rather than claiming the runtime prompt was untouched.

Report briefly: defects confirmed; changes and responsibility shifts; existing fixes retained; tests actually executed and results; any remaining blocked item with evidence; remaining live gaps; exact next action. Distinguish architecture alignment, functional verification and improved solution quality—do not claim one proves the others.

Commit and push the completed implementation and documentation to this branch after relevant checks pass. Do not force-push, overwrite unrelated work, or publish generated target-repository remediation PRs. If a material dependency blocks one part, complete the independent authorized work and document the specific blocker.
