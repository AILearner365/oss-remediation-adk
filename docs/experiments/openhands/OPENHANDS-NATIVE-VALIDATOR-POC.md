# POC 3: Native OpenHands Stop Hook to existing independent validation service

**Status:** first live Cloud Shell run was NOT_PROVEN (four REMEDIATION_FAILURE attempts, no durable PASS). Corrected synchronization fixture committed for a second run; result pending.

## Objective

Verify the native SDK/Agent Server **1.55.1** Stop Hook calls the existing
`openhands_shared.validation.SharedValidationService` contract (not another
acceptance decision engine), using a disposable, independently evaluated local
fixture. This is a bridge POC, **not** an actual Maven/OSV scan.

The service is reused for attempt counting, task identity, worktree/commit
verification, baseline artifact checks, SHA-bound repository state,
report classification, durable PASS acceptance, and rejection after
a validated workspace changes. It temporarily uses the **existing SQLite
store**. That is deliberate: removing the store safely is a separate
architecture decision, not a prerequisite to exercising real native hooks.

## Controlled setup

- The existing `tests/integration/test_openhands_shared_validation.py`
  fixture creates a small disposable Git repository, contract, baseline
  artifacts, native runtime identity, and validation store.
- The hook is a real native command invoking
  `SharedValidationService.handle_stop()`.
- A deterministic **ArtifactRunner** checks one exact marker file in the
  disposable task worktree and produces the contract-shaped validation
  report used by the existing service. It does NOT execute Maven or OSV.
- The local mock model from POC2 requests the native FinishTool.
- First attempt: marker missing -> independent service FAIL -> native DENY.
- At the following mock-model request containing native DENY feedback, a synchronous test-coordinator checkpoint first verifies the native denial event and exactly one durable failure, then writes
  the expected marker, simulating an external fix. **The agent does not
  implement the repair** in this test.
- Next attempt: independent service validates current repository state;
  if PASS, native completion is ALLOW.
- Final evidence requires a stored PASS, `verify_validated_state()`,
  native blocked/allowed events, model feedback, and finished status.

The fixture is separated from POC2 under
`/tmp/openhands-native-poc-1271-server-1551/hook-poc3-service-v2`.
Prepared task artifacts live in another dedicated temporary directory
created by the existing test fixture. No real project checkout is modified.

## First-run finding and corrected checkpoint

First evidence: `native-validator-20261018T191025Z-13d904.json`.
The native integration worked (four hook events, three DENYs, feedback to the
model), but all four independent validation attempts returned
`REMEDIATION_FAILURE`. The fourth native Stop Hook ALLOW was a **bounded
failure termination**, not validation success; accepted was false.

Likely cause: the original coordinator polled native events once per second,
while the local mock model could complete repeated FinishTool attempts before
the coordinator wrote the simulated repair file.

The second fixture (**service-v2**) replaces this race with a synchronous
checkpoint on the *next model request after native DENY feedback*. Before
returning another FinishTool call, the checkpoint requires both (a) a native
blocked Stop Hook event with exit code 2, and (b) exactly one recorded
`REMEDIATION_FAILURE`. Only then does the coordinator create the repair.
This is deterministic test synchronization, **not a remediation agent edit**.

Preserve the original POC3 fixture. Do not clean the prior state.
A later native ALLOW alone never proves acceptance: PASS still requires the
existing service's durable `PASS` result and validated Git state.

## Cloud Shell commands

Keep the existing Canvas 1.27.1 / Agent Server 1.55.1 stack running on
port **8091**, with the tested temporary LiteLLM 1.105.1 constraint.

```bash
cd ~/oss-remediation-adk
git pull --ff-only origin openhands-service-integration

python3 -m unittest discover -s tests/integration -p 'test_openhands_native_validator_poc.py' -v

python3 scripts/openhands_native_validator_poc.py run
python3 scripts/openhands_native_validator_poc.py publish
```

The offline test touches only disposable repositories. The live test
starts one separate native conversation against a **local model stub**,
without Vertex/Gemini calls, GitHub delivery, real build, or scanner.
If the live test reports `NOT_PROVEN` or `ERROR`, publish the
sanitized JSON, leave the temporary evidence intact, and investigate
native and validator events; do not erase or rerun against the same fixture.

Evidence is saved at
`~/openhands-native-poc-reports/native-validator-poc-1.55.1-service-v2.json`
and optionally pushed under
`docs/experiments/openhands/evidence/native-validator-*.json`.

## Acceptance conditions

- Native Stop Hook runs and invokes the **existing** validation service
  at least twice against the same prepared task/workspace/conversation.
- First attempt is a non-PASS durable classification and the native
  event has `blocked=true`, exit code `2`.
- The next model request contains deterministic validation feedback.
- Test coordinator's local file change is independently examined by
  the validation runner and recorded as a subsequent durable PASS.
- The existing service marks the task accepted, and the recorded Git
  repository state still verifies through `verify_validated_state()`.
- Native STOP ALLOW event and final finished status exist.

The standalone offline test also modifies the validated repo after PASS
to prove `verify_validated_state()` becomes false.

## Boundaries and next gates

This does NOT establish Maven/OSV scanner correctness, full worktree
isolation from a potentially adversarial agent, scanner or subprocess
timeout behavior, real agent-produced code changes, genuine remediation,
or production delivery. It does not replace the original
`ExistingDeterministicValidationRunner` for actual workloads.

The production-grade Stop Hook must **never** interpret native
`finished` or a hook's infrastructure failure as validation PASS.
The existing service currently permits native termination in several
non-PASS terminal failure cases; its durable acceptance status is the
security authority. Later failure-mode and retry-budget tests must
verify that distinction explicitly.

This POC is deliberately a **reuse comparison**: we can decide what
SQLite/adapter state is still necessary only after native Stop Hook
and validation behavior is proven, rather than replacing durable
evidence with an untested homegrown system.
