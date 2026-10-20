# Native preparation contract — bounded inspection result

> Historical remote Agent Server investigation, retained unchanged below. The
> product now uses the officially supported standalone SDK caller sequence:
> initialize conversation, deterministic preparation, durable COMPLETE gate,
> send_message/run, native persistence/resume. The remote /run prerequisite
> requirement is no longer the selected execution contract. See
> [current implementation and deployment limits](IMPLEMENTATION.md). No remote
> investigation or probe was repeated for this migration.

Product: **Autonomous OSS Vulnerability Remediation**. Reviewed 2026-10-20,
installed Agent Server/SDK/tools **1.55.1**, existing Canvas **1.27.1**.
**Decision: no reviewed supported mechanism satisfies all mandatory A–F
guarantees. Stop this migration and preserve the working diagnostic code.**
This is not completion of the product lifecycle integration.

## Installed source and actual API authority

Paths below are relative to the installed `openhands` package. Line references
apply to the exact source hashes recorded in
[the evidence manifest](evidence/native-preparation-1551.json), not an assumed
upstream `main` revision. No vendor source was modified or copied into product code.

| Mechanism | Source evidence | Consequence |
| --- | --- | --- |
| Conversation initialization | `sdk/conversation/impl/local_conversation.py:330–332,1270–1310,1551–1605`; `agent_server/event_service.py:1260–1274` | Explicit hooks are passed into the SDK and initialized lazily. SessionStart is called, but its return is not a required preparation verdict. Agent readiness/plugin flags are in-process; they start false in reconstructed instances. |
| SessionStart | `sdk/hooks/manager.py:157–161`; `sdk/hooks/conversation_hooks.py:323–339` | Executes with `stop_on_block=False`; processor emits events/logs but returns no blocking result. Even an intentional exit-2 denial does not abort initialization. |
| UserPromptSubmit | `sdk/hooks/conversation_hooks.py:240–290`; `sdk/agent/agent.py:707–750,920–959`; `sdk/conversation/state.py:663–674` | Exit 2 blocks the message/first step, but `pop_blocked_message()` consumes the denial. Native Stop denial can continue the loop after it has been consumed. It is not a durable baseline prerequisite checked before every inference/run/recovery. |
| Hook process failure | `sdk/hooks/executor.py:63–69,555–621` | Non-blocking HookResult on non-2 errors, missing commands and timeouts. A helper cannot turn its own failure-to-start into an exit-2 response. |
| Pre-run `execute_tool()` | `sdk/conversation/impl/local_conversation.py:3142–3188`; `.../remote_conversation.py:1824–1843` | Local capability exists, bypassing confirmation/security checks and leaving safeguards to its caller. RemoteConversation explicitly raises NotImplementedError. Local availability does not establish remote API support or automatic prerequisites. |
| Native pre-run bash | `agent_server/bash_router.py:112`; `agent_server/bash_service.py:287–303` | Conversation-associated bash endpoints exist and can run without inference, but their result is not a prerequisite of `/run`. Sequencing and checking them externally would repeat the rejected external orchestration. No command was executed through them in this review. |
| Native run | `agent_server/conversation_router.py:406–437`; `agent_server/event_service.py:1422`; `sdk/conversation/impl/local_conversation.py:1928–1948,2131–2142` | `/run` starts native execution; the reviewed route/config has no mandatory baseline-COMPLETE dependency/receipt or pre-run tool transaction. |
| Stop | `sdk/hooks/manager.py:180–199`; `sdk/hooks/conversation_hooks.py:355–389`; `sdk/conversation/impl/local_conversation.py:1963–1991,2184–2210` | Supported acceptance/feedback gate, retained. Native denial returns execution to RUNNING and continues. It operates after agent execution and cannot establish the first-inference preparation prerequisite. |

Read-only `GET /server_info` confirmed all three 1.55.1 versions. `GET
/openapi.json` confirmed no preparation fields in `StartConversationRequest`,
no request body for `/api/conversations/{conversation_id}/run`, and no remote
SDK execute-tool endpoint. The existing bash endpoints were explicitly accounted
for rather than mistaken for missing capability. No mutating API request was made.

Official references, checked alongside installed source:
[hooks](https://docs.openhands.dev/sdk/guides/hooks) documents non-blocking
SessionStart and non-blocking command errors;
[conversation API](https://docs.openhands.dev/sdk/api-reference/openhands.sdk.conversation)
documents local pre-run tool execution and caller-owned safeguards. These moving
documentation pages are supplementary; installed code/schema decides this version's behavior.

## Mandatory guarantees and decision

| Guarantee | Result in the inspected installation |
| --- | --- |
| A. Preparation inside native lifecycle | SessionStart provides lifecycle invocation; local tools/native bash provide execution facilities. None establishes the full required prerequisite contract. |
| B. COMPLETE before any inference | Nominal ordering is possible, but no enforced fail-closed prerequisite was established for the remote workflow. |
| C. Preparation failure blocks inference | Not guaranteed: SessionStart ignores denial; hook infrastructure fails open; prompt denial can be consumed before Stop-driven continuation. |
| D. Same conversation identity/evidence | Supported hook session identity and native events can bind observations. This useful facility is not proof of B/C. |
| E. Recovery cannot skip/duplicate preparation | No native preparation transaction/receipt was found. Lazy initialization can rerun SessionStart; a local custom claim alone is not an enforced native run prerequisite. |
| F. Separate trusted execution authority | Not established. Hook/native bash subprocesses execute under the server OS authority; existing `files.command()` also runs repository Maven code without an OS isolation boundary. Stripping environment variables does not prevent same-user file/credential access or build code corrupting evidence. |

The exact missing contract is a **supported, durable remote conversation
pre-inference preparation prerequisite**, fail-closed on failure-to-start/timeout
as well as negative verdicts, with a separately enforced trust domain for trusted
preparation/evidence versus repository build and agent execution. This review does
not claim that every conceivable custom agent extension is impossible; it cannot
certify one through the reviewed supported facilities and installed permissions.
Putting preparation in agent/tool constructors or a wrapper is not evidence of
that contract. No such workaround was implemented.

**No proof of the required native baseline-before-inference guarantee is claimed.**
The preserved diagnostic code checks baseline COMPLETE before attachment and
uses an external dispatch gate. That ordering remains useful offline, but does
not meet the new mandatory native ownership requirement. A successful unit test
or a single normal hook invocation cannot cure the missing failure/recovery contract.

## Focused verification (no inference)

`tests_native/test_preparation_contract.py` exercises the installed code:
SessionStart exit-2 observation without blocking; prompt exit-1/timeout failure
semantics; consumption of prompt denial followed by a Stop-continuation-style
step; explicit remote execute_tool rejection; and source hash/version matching.
The continuation probe stops at a tripwire before LLM context/metadata preparation;
it neither instantiates an LLM nor calls one. Controlled fixtures are not a live
remediation simulation. No OpenHands monkey-patching is used.

Run with the existing installed native Python:

```bash
<native-server-python> -m unittest discover -s tests_native -p test_preparation_contract.py -v
```

Verification: all 26 tests passed in the installed native runtime, including the
five contract probes. The stdlib-only suite passed 20 tests and skipped the six
SDK-dependent checks. CLI/configuration/syntax checks also passed. These results
confirm preserved diagnostic safety and the documented limits, not product readiness.

The product's deterministic validator, native instructions/tools, existing Stop
gate, draft identity checks, create-only push, claims and reconciliation are
preserved. No custom lifecycle was removed without a demonstrated replacement;
the external diagnostic sequence is explicitly retained, not renamed native.
Branch `autonomous-oss-remediation` preserves the old implementation and branch.
Target application branches, native histories and Milestone 1 evidence were untouched.
