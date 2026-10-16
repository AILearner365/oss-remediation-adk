# SBRI output acceptance notes

These notes document a read-only review of the byte-for-byte artifacts produced
by the successful standalone S4 validation. The artifacts were reused from
`/tmp/sbri-live`; the scanner was not rerun and the files were not rewritten.

## Acceptance results

| Check | Result | Evidence |
| --- | --- | --- |
| Canonical JSON parses | PASS | Python JSON parsing completed without error |
| JSON schema | PASS | `result-schema-v1.json` validation completed without error |
| Exactly four HTML tables | PASS | `table1` through `table4`; no fifth table |
| Table 1 ranking | PASS | 3.3.8 rank 1, 3.3.7 rank 2, 3.3.5 rank 3; totals match JSON |
| Table 2 severity breakdown | PASS | 20 rows cover Critical, High, Medium, Low and Unknown for four releases; every value matches JSON |
| Table 3 dependency evidence | PASS WITH PRESENTATION DISCREPANCY | 34 baseline dependencies include ownership, selected version, Boot default and fixed-version summary |
| Table 4 frozen structure | PASS | Approved nine columns appear in the approved order |
| Table 4 candidate vulnerability meaning | PASS | All 34 displayed 3.3.8 rows were compared with JSON dependency findings; `New version vulnerabilities` contains all findings under 3.3.8, not only additional findings |
| HTML/JSON consistency | PASS | Table 1 totals/ranks, all Table 2 values and all initial Table 4 candidate vulnerability cells agree with `result.json` |
| Sensitive-data review | PASS | No credentials, bearer tokens, API keys, private keys, or private URLs were found |
| Byte preservation | PASS | Source and preserved SHA-256 hashes match and `cmp` reports both files identical |

## Recorded discrepancies and limitations

1. Table 3's third header is literally `Boot {base} default`; the renderer did
   not substitute `Boot 3.3.4 default`. The column values themselves contain the
   actual Boot defaults. This artifact-retention task deliberately does not fix
   the presentation defect.
2. The HTML header does not display all header metadata requested by the frozen
   contract, including the complete requested/evaluated release list,
   profiles/modules/scopes, selected severity list, scanned-but-hidden status,
   and detailed assessment gaps. Most of this information is present in JSON.
3. Evidence references inside the preserved JSON/HTML are absolute paths under
   `/tmp/sbri-live/evidence`. Only the requested canonical JSON and HTML are
   retained here, so those raw scanner/TGF paths are not portable repository
   links. Their absence does not change the retained result or report bytes.
4. The JSON declares the snapshots comparable but does not record a precise
   advisory-database snapshot timestamp. The associated validation evidence
   records that the live baseline contained 80 findings versus A7's historical
   81 because one Medium finding was absent in the later response.
5. The live fixture contains only `BOOT_MANAGED` ownership. Other ownership
   categories are covered by focused tests/earlier evidence, not demonstrated
   by these two retained artifacts.
6. The report correctly shows `Unknown` for dependency-level fixed-version
   summaries where no finding/fix evidence exists. The run status is `SUCCESS`
   and its `errors` array is empty; compatibility remains outside the
   security-only ranking.

No frozen contract, implementation file, historical evidence, or generated
artifact content was changed during this review.
