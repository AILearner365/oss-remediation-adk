# OSS Vulnerability Remediation

## Summary

This PR remediates Critical/High OSS vulnerabilities detected by the automated OSS remediation workflow.

Remediation type: **FULL_REMEDIATION**
Verification outcome: **FULL_REMEDIATION**

Affected packages: **2**
Resolved packages: **2**
Partially resolved packages: **0**
Pending packages: **0**

Baseline findings: **2**
Resolved findings: **2**
Pending findings: **0**
New introduced findings: **0**

Baseline severity: **Critical=1, High=1**
Resolved severity: **Critical=1, High=1**
Pending severity: **Critical=0, High=0**
New introduced severity: **Critical=0, High=0**
New Critical/High introduced: **No**

This summary is based on `final/remediation-verification-report.json`, the deterministic verification artifact generated after validation.

## Remediated Vulnerabilities

| Vulnerability ID | CVE | Severity | Dependency | Old Version | New Version | Status | Reason |
|---|---|---|---|---|---|---|---|
| GHSA-599f-7c49-w659 | CVE-2022-42889 | CRITICAL | org.apache.commons:commons-text | 1.9 | 1.10.0 | RESOLVED | Planner selected version 1.10.0 and post-remediation OSV validation confirmed this finding is no longer present. |
| GHSA-4jq9-2xhw-jpx7 | CVE-2023-5072 | HIGH | org.json:json | 20230227 | 20231013 | RESOLVED | Planner selected version 20231013 and post-remediation OSV validation confirmed this finding is no longer present. |

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

The patch set was generated from the validated remediation plan and applied using exact-text Maven dependency version updates. The resulting project build and tests passed, and the remediation verification report found no pending Critical or High findings.
