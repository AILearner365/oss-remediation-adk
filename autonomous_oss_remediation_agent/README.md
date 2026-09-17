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
  "repositoryUrl": "https://github.com/example/project.git",
  "referenceBranch": "main",
  "workspaceParent": "autonomous-oss-remediation-workspaces",
  "vulnerabilityIds": ["CVE-2021-44228"],
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
    "executable": "C:/approved-tools/osv-scanner.exe",
    "version": "2.6.0",
    "sha256": "approved-executable-sha256"
  },
  "delivery": {
    "mode": "manual"
  }
}
```

Install the independent dependencies and run:

```text
python -m pip install -r autonomous_oss_remediation_agent/requirements.txt
python -m autonomous_oss_remediation_agent.cli request.json --output result.json
```

The `allowNetwork` value declares the approved runner network mode; the local backend does not claim destination-level egress enforcement.

Before the first model-backed POC, replace the repository and scanner placeholders, confirm the configured scanner version and checksum, provide the selected Gemini authentication method to the ADK process, and run only on the approved trusted-repository/dedicated-runner identity. Keep `delivery.mode` set to `manual`; the stock CLI does not enable automated GitHub delivery.

## Delivery

The stock CLI uses `ManualDeliveryAdapter` and therefore ends a validated remediation as `PARTIAL / MANUAL REVIEW REQUIRED` with `VALIDATED_MANUAL_DELIVERY_REQUIRED`.

Automated delivery requires an explicitly injected approved `DeliveryAdapter`, normally through the orchestrator's per-run `delivery_adapter_factory` so the adapter receives the run-owned process runner and trace store. The included Git-plus-GitHub-REST adapter requires a credential provider whose secret is genuinely unavailable to the remediation shell identity. Its isolation flag is a deployment attestation, not an isolation mechanism. Never mark an environment-backed credential manager or secret store as isolated when the agent's OS identity can access it. If isolation cannot be established, preflight remains in manual-delivery mode and never resolves a credential.

## Verification

```text
python -m unittest tests.unit.test_autonomous_agent_runtime tests.unit.test_autonomous_capabilities tests.unit.test_autonomous_scanner_constraints tests.unit.test_autonomous_validation_delivery -v
python -m unittest tests.integration.test_autonomous_orchestrator -v
```

The real Maven/OSV smoke test is opt-in:

```text
set RUN_AUTONOMOUS_REAL_E2E=1
set AUTONOMOUS_OSV_SCANNER=C:\approved-tools\osv-scanner.exe
python -m unittest tests.e2e.test_autonomous_real_smoke -v
```
