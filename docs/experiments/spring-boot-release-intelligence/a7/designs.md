# A7 designs

A7 compares four bounded implementations against the same Maven-selected
inventory. It does not replace candidate builds or establish a production API.

| Solution | Executable mechanism | Boundary |
| --- | --- | --- |
| S1 | `cyclonedx-maven-plugin:2.9.1:makeAggregateBom`, then OSV Scanner 2.6.0 | A second Maven resolution; native SBOM inventory is authoritative only for this solution |
| S2 | A5 pinned dependency tree plus the S1 invocation and exact coordinate/version reconciliation | A mismatch makes assessment incomplete; A5 paths explain origins |
| S3 | A5 inventory, deduplicated OSV `querybatch`, then full advisory retrieval | Package matching is not claimed scanner-equivalent; missing details make assessment incomplete |
| S4 | A5 inventory converted by `a7.minimal_cyclonedx`, structural validation, then OSV Scanner | No second Maven resolution; converter does no vulnerability interpretation |

`a7.py` also provides isolated candidate copying. It changes exactly one local
Boot parent, imported BOM, or BOM property controller. Zero or multiple
controllers produce `CANDIDATE_CONFIGURATION_AMBIGUOUS`. Every candidate is
copied from the original source, preventing X→Y→Z mutation.

Finding identity is package, selected version and advisory ID. Release
disposition matches original findings across versions by package plus advisory;
module occurrences remain separate inventory evidence. An incomplete run is
never reported clean.

The experiment intentionally adds no framework, extension interface, scanner
adapter contract, or remediation behavior.

Each mechanism is independently invocable. S1 uses the pinned Maven command in
`results.md`; S2 adds `a7_cli reconcile`; S3 uses `a7_cli osv-batch`; and S4
uses `a7_cli minimal-sbom` followed by OSV Scanner.
