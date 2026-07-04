# OSS Vulnerability Remediation

## Summary

This PR remediates Critical/High OSS vulnerabilities detected by the automated OSS remediation workflow.

Remediation type: **FULL_REMEDIATION**

## Remediated Vulnerabilities

| Vulnerability ID | CVE | Severity | Dependency | Old Version | New Version | Status | Reason |
|---|---|---|---|---|---|---|---|
| GHSA-vv7r-c36w-3prj | CVE-2025-48976 | HIGH | commons-fileupload:commons-fileupload | 1.5 | 1.6.0 | REMEDIATED | Patch set validated successfully. |
| GHSA-599f-7c49-w659 | CVE-2022-42889 | CRITICAL | org.apache.commons:commons-text | 1.9 | 1.10.0 | REMEDIATED | Patch set validated successfully. |
| GHSA-4jq9-2xhw-jpx7 | CVE-2023-5072 | HIGH | org.json:json | 20230227 | 20231013 | REMEDIATED | Patch set validated successfully. |
| GHSA-78wr-2p64-hpwj | CVE-2024-47554 | HIGH | commons-io:commons-io | 2.11.0 | N/A | REMEDIATED | DependencyManagement override removed because commons-io:commons-io is a transitive dependency introduced by commons-fileupload:commons-fileupload, and commons-fileupload:commons-fileupload is already patched in this plan. Validation must confirm whether the parent dependency upgrade resolves the transitive vulnerability. |

## Changes Made

Updated Maven dependency versions in `pom.xml` only.

No Java source code, test source code, JDK version, Maven plugin build logic, suppression, or ignore workaround changes were introduced.

## Validation

| Validation Step | Result |
|---|---|
| Baseline build | SUCCESS |
| Change scope validation | SUCCESS |
| Maven build | SUCCESS |
| Maven tests | SUCCESS |
| OSV validation | SUCCESS |
| Remaining Critical vulnerabilities | 0 |
| Remaining High vulnerabilities | 0 |
| New Critical/High vulnerabilities introduced | False |

## Notes for Reviewers

The patch set was generated from the validated remediation plan and applied using exact-text Maven dependency version updates. The resulting project build and tests passed, and post-remediation OSV validation found no remaining Critical or High vulnerabilities.
