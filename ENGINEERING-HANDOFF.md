# Autonomous OSS Vulnerability Remediation — engineering handoff

Read [PRODUCT-CONTRACT.md](PRODUCT-CONTRACT.md) fully. It governs behavior and
trust boundaries. Product branch: `autonomous-oss-remediation`, created from
verified `11431b428a69f4525679bda5880bf0a0d05137bc`. The local and remote
`openhands-native-product` branches remain preserved at that commit; no history
rewrite, old branch deletion or target-application branch change is required.

## Current engineering result

The native preparation migration is **blocked**, not implemented or live-proven.
The installed native Server/SDK 1.55.1 and actual API schema were inspected before
lifecycle changes. [The bounded investigation](docs/NATIVE-PREPARATION-BLOCKER.md)
identifies the missing prerequisite/failure/recovery/isolation contracts and
records reproducible no-model checks. No alternative orchestration engine,
wrapper, SDK patch, framework upgrade or new service was introduced.

Preserve the existing preparation, Maven/OSV graph/coverage checks, independent
validator, native prompt/Stop integration, intent/outcome records and exact-tree
GitHub draft-delivery guards. The existing external prepare/attach/run sequence
is diagnostic scaffolding, not native-owned product execution. Do not relabel it
as complete or merely combine it into a single command.

Milestone 1 evidence remains at `f72e5308704960ee911f382f96bf0b7948435216`:
native conversation `05f7716a-90bc-4ec5-a90e-01b7a4de5fa0`, Gemini, one-file
independent PASS, validated tree/base binding and actual draft PR #214. This does
not prove trusted native pre-inference preparation or real OSS remediation.

## Execution boundary and next action

No model call, new remediation PR or target modification is authorized by this
handoff. Do not proceed to a live product run while the mandatory native gate is
unresolved. The next engineering prerequisite is a verified supported native
pre-inference/recovery contract and an actual trust boundary for preparation and
repository builds. No OpenHands version change or framework comparison is
pre-approved. Existing offline safety checks remain useful independently.

Keep one autonomous reasoning/coding agent and the existing operating model:
stable task, verified facts/uncertainty, credible whole-goal candidates,
evidence-backed strategy, implementation/reassessment, self-checks, honest
intent/outcome, independent acceptance and bounded failure. Optional SBRI is
evidence, never a required Spring Boot strategy. Keep product-oriented names;
retain `native_remediation` imports and OpenHands SDK names for compatibility.
