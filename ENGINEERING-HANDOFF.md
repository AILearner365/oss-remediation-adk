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
independent acceptance and PASS-only exact-tree draft delivery. SDK owns history,
status and reasoning; application records only task/evidence/budgets/claims.
Retain all policy/scanner/coverage, intent/outcome/reassessment and delivery guards.

**Do not claim authority isolation.** State and credentials are outside the
workspace, but LocalWorkspace/TerminalTool and Maven execute as the host user.
They can access sibling state/home/credentials, create background processes, and
load repository code/plugins. A working directory is not a process/filesystem
boundary. No agent-facing acceptance/delivery tool is provided, which does not
remove that physical authority.

The mandatory inability of agent/build code to modify trusted decisions or obtain
delivery credentials is therefore unsupported in this local deployment. Existing
production build/acceptance, dispatch and delivery paths fail closed with a
specific Blocked error. There is deliberately no security-override flag. Offline
fixtures may replace that guard to verify the retained contracts; this is not a
runtime alternative, live authorization or security proof.

31 focused tests pass in installed SDK Python (24 stdlib product/local checks).
Real SDK tests cover idle persistence, retained Stop denial, evidence-tool use,
host workspace commands and persistent terminal invocation without inference.
Maven/OSV stand-ins and controlled outputs do not prove real analysis. The SDK
workspace command helper emits non-fatal ResourceWarnings in this installation;
vendor code is untouched.

See [operations](docs/OPERATIONS.md) and [proof map](docs/IMPLEMENTATION.md).
The unresolved decision is the mandatory authority requirement in the selected
same-user host environment, not SDK lifecycle support or image provisioning.
Do not invent infrastructure, weaken acceptance, run Gemini or create target PRs.
