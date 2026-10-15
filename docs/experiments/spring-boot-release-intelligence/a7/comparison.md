# A7 comparison

| Criterion | S1 | S2 | S3 | S4 |
| --- | --- | --- | --- | --- |
| Maven-selected inventory | Native plugin resolution | Native plus A5 reconciliation | A5 | A5 |
| Paths | No | A5 | A5 | A5 |
| Scanner semantics | OSV Scanner | OSV Scanner | Not equivalent; API semantics | OSV Scanner |
| Second resolver | Yes | Yes | No | No |
| Focused inventory correctness | 34 components | exact 34/34 | queried all 34 | exact 34/34 |
| Focused scanner equivalence | reference side | same native scan | not claimed | exact 81/81 pairs |
| Application JAR download | 34/34 | same overhead | A5 boundary | A5 boundary |
| Main risk | duplicated resolution and packaged/metadata scope | cost without demonstrated added correctness | advisory interpretation and detail fan-out | converter/schema and scanner-input maintenance |

S1 demonstrates that native CycloneDX works, but it downloaded every selected
application JAR in the focused fixture. S2 retained A5 explanation and found no
inventory difference, while its combined fresh cost was not measured. S3
successfully retrieved live details, but required 81 API calls and is not
scanner-equivalent. S4 used a 76% smaller SBOM than S1 and matched all 81
scanner identities without a second Maven mechanism; that result is limited to
one baseline configuration.

No performance ranking is fair yet: collection stages were not measured from
equivalent fresh/warm caches as complete solution pipelines, and peak memory is
missing.
