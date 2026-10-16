# SBRI integration with OpenHands Gate 2

Status: implemented on `spring-boot-release-intelligence-feasibility`, which is
a direct descendant of the current `openhands-poc-evaluation` tip. No divergent
branch merge is required.

## Integration point

The existing Gate-2 runner invokes SBRI after it has verified the clean target
worktree, loaded the deterministic baseline, configured the Stop Hook and
prepared terminal launchers, but before `conversation.send_message` and the
first agent action. This is the narrow point where candidate evidence can
inform engineering reasoning without adding a lifecycle stage or replacing the
agent's strategy decision.

The sequence remains:

```text
clean task worktree -> deterministic baseline -> applicable pre-edit SBRI
-> one OpenHands reasoning/coding agent -> agent self-validation
-> independent Stop Hook validator -> retained evidence
```

The deterministic validator is unchanged and evaluates the actual modified
application. SBRI's hypothetical candidate graphs cannot satisfy completion.

## Applicability and release discovery

SBRI runs only when both conditions hold:

1. the task describes dependency/security remediation; and
2. the root Maven POM has one unambiguous Spring Boot parent/BOM controller.

Unrelated tasks and non-Spring Maven repositories receive no injected SBRI
context. Applicability failure is recorded and is not interpreted as evidence
against a Spring Boot strategy.

The harness discovers current stable forward patch releases from Spring Boot's
Maven Central metadata. It evaluates up to the latest three releases in the
baseline major/minor line, excluding milestones, release candidates,
snapshots, downgrades and invented versions. The actual discovered versions are
passed through the existing `sbri evaluate --releases` interface. A run can
instead use ordinary SBRI JSON configuration via `--sbri-config`.

## Environment and tool access

The control repository remains the installed SBRI implementation. The runner
adds a small `sbri` launcher to the existing harness-owned terminal-launcher
directory and supplies the control repository on `PYTHONPATH`. OpenHands can
therefore call the documented CLI from the application workspace without
copying SBRI into or modifying that workspace.

Pre-edit outputs live under the persistent task state:

```text
~/.openhands/gate2/task-NN-stop-hook/sbri/<input-fingerprint>/
  execution.json
  command.log
  agent-summary.txt
  agent-summary.json
  output/result.json
  output/report.html
  output/evidence/
```

The source commit, every non-generated POM hash, candidate set, scanner and
configuration participate in the fingerprint. An identical request reuses the
retained result; changed inputs produce a different directory. Conversation
persistence, the task message and `sbri/latest.json` keep references available
after context condensation or recovery.

Disable pre-edit integration with `--no-sbri` or `OPENHANDS_SBRI=0`. This does
not remove the standalone CLI launcher.

## Agent-facing evidence

The injected summary is bounded. It contains baseline/evaluated releases,
complete/partial status, original/addressed/remaining/new/total counts,
remaining Critical+High counts, security ranking, a bounded list of selected
version and ownership changes, errors, and absolute artifact paths. Full JSON,
HTML, Maven graphs and scanner responses are referenced rather than dumped into
model context.

The message explicitly states that rank 1 is security evidence, not an upgrade
instruction. It prompts the agent to combine SBRI with Maven ownership,
application compatibility, task constraints and other current evidence and to
choose among credible framework, targeted, override, combined or other
justified strategies. The existing decision Skill contains the same boundary.

Delivery before the agent run is recorded deterministically. Actual use and
consideration before the first dependency edit must be established from the
observable trajectory; the harness does not infer reasoning merely from prompt
delivery.

## Exit and failure handling

- `0`: complete evidence is summarized and supplied.
- `3`: partial successful results and structured errors are preserved and
  supplied with an explicit partial status.
- `2` or other failure: command evidence is retained, no zero-finding claim is
  made, and the agent is told that failure does not prove upgrades impossible.

No scanner fallback occurs. A missing configured scanner remains a concrete
failure. SBRI's baseline-failure CLI path now returns its documented code `2`.

## Durable evidence and overhead

The orchestrator publishes `latest.json`, bounded summaries, command log,
canonical JSON/HTML and operative Maven/scanner evidence. Maven repositories,
materialized candidate workspaces and HTTP caches remain in task-local evidence
but are excluded from the Git review bundle.

`execution.json` records wall time, sampled process-tree peak RSS, total output
size, Maven-cache/JAR counts and bytes, summary characters and an approximate
token count, plus whether duplicate execution was avoided.

## Validation boundary and limitations

- SBRI does not select or apply remediation.
- The security ranking does not establish Java, build, test, packaging, API or
  runtime compatibility.
- Forward discovery is intentionally bounded to stable patches in the current
  line; the agent may investigate other task-permitted strategies/releases.
- SBRI collection populates an output-local Maven cache and may require network
  access. Failure is non-authoritative investigation evidence, not completion.
- Whether the model inspected or relied on SBRI is observable only in a live
  trajectory, not proven by offline delivery tests.
