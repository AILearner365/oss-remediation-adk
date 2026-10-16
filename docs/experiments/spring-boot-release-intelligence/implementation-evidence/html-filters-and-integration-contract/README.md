# HTML filters and integration-contract validation

This focused evidence set validates the SBRI presentation enhancement and
external-tool contract without rerunning Maven or OSV Scanner.

`report.html` was regenerated from the unchanged canonical real-application
result at:

`../maven-multimodule-main-runrunning/result.json`

That source JSON has SHA-256
`6fc2e2d8e5740c4fca908ed1063b27b626ba911c0e56acf913f550fe99018b6a`.
The enhanced HTML has SHA-256
`ff00f720c9ec88fb186eeb195ce0a272f02d6cafbd19015e1731200eea56ca70`.

The report remains a single portable HTML file with embedded vanilla
JavaScript and CSS. It makes no network requests and contains exactly four
tables. See `filter-acceptance.md`, `integration-contract-acceptance.md`, and
`test-results.json` for the exercised behavior and limitations.
