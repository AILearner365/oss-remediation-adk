from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RemediationPolicy:
    severity_scope: list[str] = field(default_factory=lambda: ["CRITICAL", "HIGH"])
    max_attempts: int = 3
    max_additional_investigation_requests_per_attempt: int = 2
    allow_partial_pr: bool = True
    pr_creation_mode: str = "AUTO"
    create_draft_pr: bool = True
    require_validated_patch_set_for_pr: bool = True
    allow_manual_approval_pr_creation: bool = False
    allowed_file_patterns: list[str] = field(default_factory=lambda: ["**/pom.xml"])
    blocked_change_types: list[str] = field(default_factory=lambda: [
        "JAVA_SOURCE_CHANGE",
        "TEST_SOURCE_CHANGE",
        "JDK_VERSION_CHANGE",
        "PLUGIN_BUILD_LOGIC_CHANGE",
        "SUPPRESSION_OR_IGNORE_WORKAROUND",
        "FULL_POM_FORMATTING_REWRITE",
    ])
    allowed_patch_change_types: list[str] = field(default_factory=lambda: [
        "DEPENDENCY_VERSION_VALUE",
        "MAVEN_PROPERTY_VERSION_VALUE",
        "DEPENDENCY_MANAGEMENT_VERSION_VALUE",
        "DEPENDENCY_MANAGEMENT_OVERRIDE",
        "PARENT_POM_VERSION_VALUE",
    ])

    @classmethod
    def load(cls, path: str | Path | None = None) -> "RemediationPolicy":
        if path is None or not Path(path).exists():
            return cls()
        raw = Path(path).read_text(encoding="utf-8")
        policy = cls()
        current_key = None
        lists: dict[str, list[str]] = {}
        nested: dict[str, dict[str, str]] = {}
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.endswith(":"):
                current_key = stripped[:-1]
                lists[current_key] = []
                nested[current_key] = {}
                continue
            if current_key and stripped.startswith("-"):
                lists[current_key].append(stripped[1:].strip().strip('"'))
                continue
            if ":" in stripped:
                key, value = [part.strip() for part in stripped.split(":", 1)]
                value = value.strip('"')
                if current_key and current_key == "prCreationPolicy":
                    nested[current_key][key] = value
                    continue
                if key == "maxAttempts":
                    policy.max_attempts = int(value)
                elif key == "maxAdditionalInvestigationRequestsPerAttempt":
                    policy.max_additional_investigation_requests_per_attempt = int(value)
                elif key == "allowPartialPr":
                    policy.allow_partial_pr = value.lower() == "true"
                elif key == "prCreationMode":
                    policy.pr_creation_mode = value.upper()
                elif key == "createDraftPr":
                    policy.create_draft_pr = value.lower() == "true"
                elif key == "requireValidatedPatchSetForPr":
                    policy.require_validated_patch_set_for_pr = value.lower() == "true"
                elif key == "allowManualApprovalPrCreation":
                    policy.allow_manual_approval_pr_creation = value.lower() == "true"
                current_key = None
        pr_creation_policy = nested.get("prCreationPolicy", {})
        if pr_creation_policy:
            if "mode" in pr_creation_policy:
                policy.pr_creation_mode = pr_creation_policy["mode"].upper()
            if "createDraftPr" in pr_creation_policy:
                policy.create_draft_pr = pr_creation_policy["createDraftPr"].lower() == "true"
            if "requireValidatedPatchSetForPr" in pr_creation_policy:
                policy.require_validated_patch_set_for_pr = pr_creation_policy["requireValidatedPatchSetForPr"].lower() == "true"
            if "allowManualApprovalPrCreation" in pr_creation_policy:
                policy.allow_manual_approval_pr_creation = pr_creation_policy["allowManualApprovalPrCreation"].lower() == "true"
        if lists.get("severityScope"):
            policy.severity_scope = lists["severityScope"]
        if lists.get("allowedFilePatterns"):
            policy.allowed_file_patterns = lists["allowedFilePatterns"]
        if lists.get("blockedChangeTypes"):
            policy.blocked_change_types = lists["blockedChangeTypes"]
        if lists.get("allowedPatchChangeTypes"):
            policy.allowed_patch_change_types = lists["allowedPatchChangeTypes"]
        return policy

    def to_dict(self) -> dict:
        return {
            "severityScope": self.severity_scope,
            "maxAttempts": self.max_attempts,
            "maxAdditionalInvestigationRequestsPerAttempt": self.max_additional_investigation_requests_per_attempt,
            "allowPartialPr": self.allow_partial_pr,
            "prCreationPolicy": {
                "mode": self.pr_creation_mode,
                "createDraftPr": self.create_draft_pr,
                "requireValidatedPatchSetForPr": self.require_validated_patch_set_for_pr,
                "allowManualApprovalPrCreation": self.allow_manual_approval_pr_creation,
            },
            "allowedFilePatterns": self.allowed_file_patterns,
            "blockedChangeTypes": self.blocked_change_types,
            "allowedPatchChangeTypes": self.allowed_patch_change_types,
        }
