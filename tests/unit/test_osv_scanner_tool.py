import unittest

from oss_remediation_agent.tools.osv_scanner_tool import normalize_osv_findings


class OSVScannerToolTests(unittest.TestCase):
    def test_osv_normalization_filters_maven_high(self):
        raw = {
            "results": [
                {
                    "packages": [
                        {
                            "package": {"ecosystem": "Maven", "name": "org.yaml:snakeyaml", "version": "1.33"},
                            "vulnerabilities": [
                                {
                                    "id": "GHSA-xxxx",
                                    "aliases": ["CVE-2026-0001"],
                                    "database_specific": {"severity": "HIGH"},
                                    "affected": [{"ranges": [{"events": [{"fixed": "2.2"}]}]}],
                                }
                            ],
                        }
                    ]
                }
            ]
        }
        findings = normalize_osv_findings(raw, ["CRITICAL", "HIGH"], "raw.json")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["dependency"]["packageName"], "org.yaml:snakeyaml")
        self.assertEqual(findings[0]["fixedVersions"], ["2.2"])


if __name__ == "__main__":
    unittest.main()
