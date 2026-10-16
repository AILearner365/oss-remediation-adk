# Spring Boot Release Intelligence — approved output/report contract v1

Status: **Frozen for presentation and information requirements** (2026-10-15). This is a contract/design snapshot, not a claim that all report renderers and scanner integrations are implemented. Do not change the four table shapes without explicit approval. The examples below are **illustrative**, not A7 per-dependency evidence.

## Goal and scope

Compare a real application's **original Spring Boot release** against each eligible release independently, preserving existing overrides, exclusions, profiles, modules, unrelated management and other configuration. Resolve **Maven-selected** dependencies and scan the *complete applicable inventory* for each release, not only vulnerable baseline packages. The original source is unchanged. No automatic remediation, compatibility approval or regression-risk claims.

Default supported implementation: A5 Maven-native dependency graph (TGF) -> deterministic minimal CycloneDX inventory -> OSV Scanner (S4). A7 selected this collector for its bounded tested scope.

## Canonical outputs

- `result.json` — versioned, authoritative, machine-readable result for CI/agents/KAI/APM; contains every assessed release, per-severity counts, selected dependency records, ownership, advisory details, evidence, errors and security-only ranking.
- `report.html` — human-readable, generated solely from the same JSON; tables 1–4 plus brief override-investigation notes, with drill-down details. Markdown may be an **optional renderer**, not a third independent calculation.
- `evidence/` — when retention is enabled, original scanner/Maven reports and reproducible error logs, referenced by paths and digests. Do not embed enormous raw outputs into the canonical JSON.

## Report header

Application; original Spring Boot version; requested/evaluated releases; scanner/provider and version; Maven modules/profiles/scopes; selected severity types; whether other severities were scanned-but-hidden or not assessed; evidence/snapshot comparability; assessment gaps. No scan failure can be displayed as zero vulnerabilities.

## Table 1 — Overall release comparison + ranking (approved)

| Rank | Spring Boot | Original | Addressed | Remaining | New | Total | Recommendation |
|---|---|---:|---:|---:|---:|---:|---|
| — | 3.3.4 (Base) | 20 | — | 20 | — | 20 | Baseline |
| 1 | 3.3.8 | 20 | 8 | 12 | 0 | 12 | Preferred — best measured security result |
| 2 | 3.3.7 | 20 | 6 | 14 | 0 | 14 | Second |
| 3 | 3.3.5 | 20 | 4 | 16 | 0 | 16 | Third |

Numbers are illustrative. Rank *only successfully assessed releases* using actual scanned findings, selected severity and transparent severity-first considerations; do **not** invent a weighted 0–100 score, rely solely on totals when severity differs, or count speculative override outcomes. Explain ties/tradeoffs. Do not imply Java/build/runtime compatibility is proven.

## Table 2 — Per-severity release comparison (approved)

| Spring Boot | Severity | Original | Addressed | Remaining | New | Total |
|---|---|---:|---:|---:|---:|---:|
| 3.3.4 (Base) | Critical | 2 | — | 2 | — | 2 |
|  | High | 4 | — | 4 | — | 4 |
| 3.3.5 | Critical | 2 | 0 | 2 | 0 | 2 |
|  | High | 4 | 1 | 3 | 0 | 3 |
| 3.3.7 | Critical | 2 | 1 | 1 | 0 | 1 |
|  | High | 4 | 1 | 3 | 1 | 4 |
| 3.3.8 | Critical | 2 | 1 | 1 | 0 | 1 |
|  | High | 4 | 2 | 2 | 1 | 3 |

This is an *illustrative layout* for only Critical/High. Real results include every requested severity (Critical/High/Medium/Low/Unknown) and reconcile with Table 1. Severity filtering is an explicit input; clarify whether other severities were evaluated but filtered or never assessed.

## Table 3 — Original dependency snapshot (approved)

| Dependency | Control / ownership | Boot 3.3.4 default | Maven-selected | Known fixed version | Critical | High |
|---|---|---|---|---|---:|---:|
| Tomcat | Boot-managed, overridden | 10.1.31 | 10.1.30 | 10.1.32* | 0 | 2 |
| Spring Security | Boot-managed | 6.3.3 | 6.3.3 | 6.3.4* | 1 | 0 |
| Library A | Independent direct | Not managed | 2.0 | 2.3* | 0 | 1 |
| Library B | Other BOM-managed | Not managed | 4.1 | 4.3* | 1 | 1 |
| **Total findings** | | | | | **2** | **4** |

All values illustrative. `Known fixed version` is a human-readable summary; actual fixed evidence remains **per advisory**, potentially multiple or unknown. Baseline ownership/control is captured before upgrade and can change in subsequent versions.

## Table 4 — Frozen dependency comparison (nine columns, approved verbatim)

| Dependency | Dependency Ownership | Boot 3.3.4 selected | Boot 3.3.8 default | Boot 3.3.8 selected | Known fixed version | Base vulnerabilities | New version vulnerabilities | Outcome |
|---|---|---|---|---|---|---|---|---|
| Tomcat | Boot-managed, overridden | 10.1.30 | 10.1.34 | **10.1.30** | 10.1.32* | 2 High | 2 High | Remains — overridden |
| Spring Security | Boot-managed | 6.3.3 | 6.3.4 | **6.3.4** | 6.3.4* | 1 Critical | 0 | Addressed |
| Library A | Independent direct | 2.0 | — | **2.0** | 2.3* | 1 High | 1 High | Remains — independent |
| Library B | Other BOM-managed | 4.1 | — | **4.1** | 4.3* | 1 Critical, 1 High | 1 Critical, 1 High | Remains — other BOM |

**Do not rearrange columns or replace this with paired rows.** Version headers adapt to the original and evaluated Spring Boot versions. `New version vulnerabilities` means **all findings present under the evaluated release**, *not* newly introduced findings. The `New` column in Tables 1–2 is newly introduced/advisory findings. Selected severity labels appear in vulnerability-count cells. The ownership cell reports the evaluated configuration; original ownership/control is preserved in Table 3 and canonical JSON. Differences in ownership must be available as evidence/drill-down. Include packages introduced/removed from resolved graph. Fixed versions and all figures illustrative.

## Short override investigation note (below Table 1 or relevant Table 4 dependency)

Example: “Spring Boot 3.3.8 manages Tomcat 10.1.34, but the application selects 10.1.30 via an override. Advisory evidence suggests the default is outside the affected range for [named findings]. Worth investigating; removing the override has **not** been tested.”

Notes do **not** modify rankings, addressed counts, totals or claim compatibility. Compare actual advisory affected ranges, not naive lexical/numeric version ordering. Do not automatically remove overrides or perform what-if runs.

## JSON information contract (v1 design)

One canonical representation stores, at minimum:
- `schema_version`, application/project and baseline description; scanner/provider, method, tool versions, coverage and advisory snapshot metadata; Maven settings/profiles/modules/scopes and requested severity filter.
- `releases[]`: version, assessment completeness/errors, `counts` for original/addressed/remaining/new/total, *each by requested severity*, rank and short security-only recommendation/rationale, and references to dependency/evidence records.
- `dependencies[]` for baseline and each assessed release: Maven package coordinates and module occurrences, dependency paths, direct/transitive relationship, management class (Boot, Boot overridden, other parent/BOM, independent, ambiguous), governing declaration/reference, Boot-managed default when applicable, **actual Maven-selected version**, introduced/removed changes and limitations.
- `findings[]`: canonical finding identity (package + advisory with alias reconciliation), scanner origin, severity/score as reported, affected package version, affected/fix evidence per advisory (including unknown), per-release presence/disposition (addressed, remaining, additional/new), references to raw evidence; no duplicate counts from multiple paths/modules.
- `errors[]`: actual stage/tool error, affected release, command/step and evidence/log location; retain successful releases. A minimal machine-readable success/partial/failure indicator exists to prevent incomplete results appearing clean.

Arithmetic for comparable snapshots: original = addressed + remaining, and evaluated total = remaining + new, under documented canonical finding identity and severity treatment. Changed advisory feeds/suppression rules can make comparisons non-equivalent; mark limits rather than invent resolution.

## Scanner interchange decision

**Primary standard: CycloneDX JSON** package inventory and, when the scanner emits them, CycloneDX vulnerability records. A7's minimal generator was schema-validated against **CycloneDX 1.5**; do not change versions silently.

**Secondary accepted format: SARIF 2.1.0, only when a validated mapping supplies dependable Maven package identity, selected version, advisory identity, severity and scan scope.** SARIF compliance alone is not sufficient to compare package vulnerabilities. Keep the original scanner report.

- Default execution: existing S4 + OSV Scanner, already tested.
- Future scanner onboarding: prefer standard CycloneDX vulnerability report or validated SARIF report reader; use vendor-native CLI/auth/environment, including JFrog `jf sbom-enrich <sbom-path>` where supported by the installed versions. A declarative trusted command/wrapper may provide reports, but do not claim every scanner accepts a generated SBOM or preserves no-JAR footprint.
- **JFrog compatibility is a validation task, not a proven integration**: exercise real enriched output and ensure `components`, `vulnerabilities[].affects`, advisory identity, severity/fixed evidence and coverage can be correlated to Maven-selected packages. Record latency/storage/extra downloads.
- Do not write one ever-growing proprietary scanner-specific comparison engine; map the small necessary fields at the interchange boundary, keeping scanner-native evidence. Cross-vendor finding totals must not be compared as equivalent without matching scope, provider/policy and snapshot.

## Frozen invariants and handoff

Exactly **four mandatory tables**, with rank/recommendation in Table 1; no fifth ranking table. Machine-readable JSON is authoritative; HTML is the human rendering. Preserve the original application and independent per-release materialization. Security-only ranking is **not** final remediation, Java compatibility, WAR viability or build/test certification.

Next task: (1) record this contract; (2) validate CycloneDX vulnerability interchange with OSV and a real JFrog sample (plus optional SARIF quality check) before promising configuration-only onboarding; (3) implement canonical JSON and a single HTML renderer using the **existing S4 mechanism**, with focused tests for all four table shapes, severity filters, ownership and failure behavior. Historical A1–A7 evidence must remain untouched.

References: https://cyclonedx.org/specification/overview/ ; https://docs.oasis-open.org/sarif/sarif/v2.1.0/os/sarif-v2.1.0-os.html ; https://docs.jfrog.com/security/docs/enrich-your-sbom-jsons-xmls ; https://github.com/google/osv-scanner/blob/main/docs/output.md .
