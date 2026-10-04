# Preliminary Run Contract

> Initial run configuration captured before repository preparation and baseline discovery are complete. It records the task inputs, configured constraints, budgets, commands, completion criteria, and other information known when the run begins. Information that depends on repository preparation or baseline discovery may still be unavailable or preliminary.

{
  "baseline": null,
  "baselineCommandEvidence": [],
  "budgets": {
    "command_timeout_seconds": 1800,
    "max_cycles": 4,
    "max_llm_calls_per_turn": 60,
    "max_returned_output_chars": 3000,
    "max_tool_calls": 80,
    "model_turn_timeout_seconds": 1800,
    "overall_timeout_seconds": 7200
  },
  "completionCriteria": [
    "required build/test/startup commands pass",
    "fresh deterministic vulnerability scan succeeds",
    "requested target findings are absent",
    "no new prohibited findings are introduced",
    "typed constraints remain satisfied"
  ],
  "constraints": {
    "allowed_paths": [],
    "engineering_constraints": [],
    "informational_constraints": [],
    "prohibit_suppressions": true,
    "prohibited_new_severities": [
      "CRITICAL",
      "HIGH"
    ],
    "protected_java_version": null,
    "protected_paths": [],
    "protected_spring_boot_version": null,
    "version_policies": {
      "spring_boot": {
        "allow_downgrade": false,
        "allow_major": false,
        "allow_minor": true,
        "allow_patch": true,
        "approved_versions": [],
        "required_version": null
      }
    }
  },
  "objective": {
    "severityScope": [
      "CRITICAL",
      "HIGH"
    ],
    "vulnerabilityIds": []
  },
  "requiredCommands": {
    "build": [
      "mvn clean verify"
    ],
    "startup": [],
    "test": []
  }
}

# Final Resolution

## Final outcome

FAILED

## Original problem

{"baseline": null, "baselineCommandEvidence": [], "budgets": {"command_timeout_seconds": 1800, "max_cycles": 4, "max_llm_calls_per_turn": 60, "max_returned_output_chars": 3000, "max_tool_calls": 80, "model_turn_timeout_seconds": 1800, "overall_timeout_seconds": 7200}, "completionCriteria": ["required build/test/startup commands pass", "fresh deterministic vulnerability scan succeeds", "requested target findings are absent", "no new prohibited findings are introduced", "typed constraints remain satisfied"], "constraints": {"allowed_paths": [], "engineering_constraints": [], "informational_constraints": [], "prohibit_suppressions": true, "prohibited_new_severities": ["CRITICAL", "HIGH"], "protected_java_version": null, "protected_paths": [], "protected_spring_boot_version": null, "version_policies": {"spring_boot": {"allow_downgrade": false, "allow_major": false, "allow_minor": true, "allow_patch": true, "approved_versions": [], "required_version": null}}}, "objective": {"severityScope": ["CRITICAL", "HIGH"], "vulnerabilityIds": []}, "requiredCommands": {"build": ["mvn clean verify"], "startup": [], "test": []}}

## Final interpreted resolution

Deterministic validation status and capture quality are reported separately. Run-level capture status: `MISSING`.

Independent validation did not run.

## Reconciliation with the accepted model Outcome

The accepted Cycle Outcome remains historical model testimony. Its status was `not captured`; it is not a fresh deterministic finding. Reconciliation against the latest independent validation:

- No independent validation available.

## Accepted model account of the implemented approach (historical claim)

No accepted Cycle Outcome described the implementation result.

## How the approach evolved

- No remediation cycle was captured.

## Final requirement coverage

### Satisfied

- None established.

- Model-reported coverage remains part of the accepted Implementation Result; only explicitly mapped deterministic checks are authoritative.

### Conditional

- Any model-reported conditional or unverified coverage remains non-authoritative pending deterministic evidence.

### Unresolved

- None established.

### Not applicable

- None established beyond the accepted model report and deterministic checks.

## Final evidence

- Deterministic validation did not run.

## Constraints and known risks

Run-level capture quality `MISSING`; delivery eligibility `NOT_DELIVERY_ELIGIBLE`.

Model-reported constraint, compatibility, regression, and risk information remains in the accepted Implementation Result above as historical claims; deterministic checks remain authoritative within their stated scope.

## Partial-remediation disclosure

Not applicable.

## Delivery result

No automatic delivery was performed.

## Remaining limitations

Restart/resume reconstruction is not implemented; machine events and the append-only journal remain available for audit.

## Final conclusion

Final outcome is `FAILED`; this does not override the separate deterministic validation, capture, or delivery states.

