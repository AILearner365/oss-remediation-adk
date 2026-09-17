# Autonomous OSS Remediation POC

This package implements the approved single-agent autonomous remediation design independently from `oss_remediation_agent`.

## Runtime Boundary

The host-native shell is permitted only when all three request flags are explicitly true:

- `runtimePolicy.trustedRepository`
- `runtimePolicy.dedicatedRunner`
- `runtimePolicy.enableAutonomousShell`

This preflight is an operational gate, not hard filesystem or process containment. The dedicated runner identity must be least privilege, contain no unrelated sensitive data, and have no delivery credential or credential store reachable by agent-run shell/build/script execution. Destination-level filesystem, process, or network isolation requires separately approved runner infrastructure.

## Scanner Modes

The deterministic lifecycle, never the LLM, selects OSV Scanner.

- `configured`: resolves a configured executable, verifies an optional expected version/checksum, records its absolute path and digest, and rechecks that digest before every scan.
- `provision`: downloads an approved pinned artifact into the run tools directory and requires `version`, `downloadUrl`, and `sha256` before extraction and execution.

An unavailable, unexecutable, changed, or unrecognizable scanner fails closed.

Multi-module Maven scanning requires OSV Scanner 2.4.0 or newer. Earlier releases do not include the upstream local-reactor-module resolution fix and are rejected rather than allowing an incomplete scan to appear clean.

## Request Example

```json
{
  "repositoryUrl": "https://github.com/AILearner365/maven-multimodule-app",
  "referenceBranch": "main-runrunning",
  "workspaceParent": "autonomous-oss-remediation-workspaces",
  "vulnerabilityIds": [],
  "severityScope": ["CRITICAL", "HIGH"],
  "buildCommands": ["mvn clean verify"],
  "model": "gemini-2.5-flash",
  "budget": {
    "maxCycles": 3,
    "maxToolCalls": 80,
    "maxLlmCallsPerTurn": 40,
    "commandTimeoutSeconds": 1800,
    "modelTurnTimeoutSeconds": 1800,
    "overallTimeoutSeconds": 7200,
    "maxReturnedOutputChars": 30000
  },
  "runtimePolicy": {
    "trustedRepository": true,
    "dedicatedRunner": true,
    "enableAutonomousShell": true,
    "allowNetwork": true
  },
  "scanner": {
    "mode": "configured",
    "executable": "/home/kavya_parivarababu/bin/osv-scanner",
    "version": "2.6.0",
    "sha256": "ca69b3d3cd08f889a49dc0a383122f71cc528b83803671df5fd874d97485b108"
  },
  "constraints": {
    "prohibit_suppressions": true,
    "version_policies": {
      "spring_boot": {
        "allow_patch": true,
        "allow_minor": true,
        "allow_major": false,
        "allow_downgrade": false,
        "approved_versions": [],
        "required_version": null
      }
    }
  },
  "delivery": {
    "mode": "auto",
    "adapter": "github-rest",
    "branch_prefix": "autonomous-oss-remediation",
    "draft": true,
    "github_api_base": "https://api.github.com"
  }
}
```

Install the independent dependencies and run:

```text
python -m pip install -r autonomous_oss_remediation_agent/requirements.txt
export GH_TOKEN="<short-lived-token-with-repository-write-access>"
python -m autonomous_oss_remediation_agent.cli request.json --output result.json
```

In PowerShell, set the token with `$env:GH_TOKEN = "<short-lived-token-with-repository-write-access>"` before running the CLI.

The `allowNetwork` value declares the approved runner network mode; the local backend does not claim destination-level egress enforcement.

## Spring Boot Version Policy

Spring Boot version movement is checked against the captured baseline after the agent finishes. The default policy allows stable numeric patch and minor upgrades, rejects major upgrades and downgrades, and permits unchanged versions. For example, from `3.5.0`, `3.5.1` and `3.6.0` pass while `4.0.0` and `3.4.9` fail.

- `approved_versions` lists exact otherwise-disallowed major-upgrade destinations. It does not authorize downgrades.
- `required_version` requires the final concrete Spring Boot version to exactly match that value.
- Legacy `protected_spring_boot_version` remains supported as an exact required version and takes precedence over `required_version`.
- Stable dot-separated numeric versions are compared component-wise. Unparseable qualifiers or structural declaration changes fail closed.
- Java version protection remains unchanged and exact; this focused policy applies only to Spring Boot.

The agent receives this policy as an allowed boundary and chooses whether and how to upgrade. Deterministic validation independently emits `spring_boot_version_policy` evidence containing the component, baseline and final versions, applicable policy, detected change type, pass/fail value, and reason.

## Target Selection

- When `vulnerabilityIds` is non-empty, only baseline findings matching one of those IDs or aliases and `severityScope` are remediation targets.
- If none match, the run stops before invoking the model with `REQUESTED_VULNERABILITY_NOT_FOUND` and preserves the completed baseline as evidence.
- When `vulnerabilityIds` is empty, every baseline finding matching `severityScope` is a remediation target.
- Validation continues to reject newly introduced findings in the prohibited severities independently of target selection.

Before the first model-backed POC, replace the repository and scanner placeholders, confirm the configured scanner version and checksum, provide the selected Gemini authentication method to the ADK process, and run only on the approved trusted-repository/dedicated-runner identity.

## Delivery

The stock CLI uses `ManualDeliveryAdapter` when `delivery.mode` is not `auto`. For automatic GitHub delivery, set `delivery.mode` to `auto`, select `github`, `github-rest`, or `git+github-rest`, and provide `GH_TOKEN` (preferred) or `GITHUB_TOKEN` to the runner process. The token must have permission to push a branch and create a pull request in the target repository.

The CLI creates the Git-plus-GitHub-REST adapter through the orchestrator's per-run `delivery_adapter_factory`. Environment credentials are withheld from the model-controlled shell by the sanitized agent environment and are resolved only after deterministic validation succeeds. The delivery adapter supplies the token to `git push` through a temporary askpass helper and sends it directly in the GitHub REST authorization header; the token is not included in command arguments or trace evidence. If neither token variable is present, preflight remains in manual-delivery mode and never attempts delivery. This is process-level separation rather than an operating-system security boundary, so use a dedicated runner and a narrowly scoped, short-lived token.

## Verification

```text
python -m unittest tests.unit.test_autonomous_agent_runtime tests.unit.test_autonomous_capabilities tests.unit.test_autonomous_scanner_constraints tests.unit.test_autonomous_spring_boot_policy tests.unit.test_autonomous_validation_delivery -v
python -m unittest tests.integration.test_autonomous_orchestrator -v
```

The real Maven/OSV smoke test is opt-in:

```text
set RUN_AUTONOMOUS_REAL_E2E=1
set AUTONOMOUS_OSV_SCANNER=C:\approved-tools\osv-scanner.exe
python -m unittest tests.e2e.test_autonomous_real_smoke -v
```
