from __future__ import annotations

from autonomous_oss_remediation_agent.deterministic.validation import (
    _classify_target_findings,
    _target_comparison_coverage,
)
from autonomous_oss_remediation_agent.models import (
    CommandResult,
    ScanOutcome,
    ScanReport,
    VulnerabilityFinding,
)


def _finding(version: str = "1.0") -> VulnerabilityFinding:
    return VulnerabilityFinding(
        vulnerability_id="GHSA-test-0000-0000",
        aliases=("CVE-2099-0001",),
        severity="HIGH",
        group_id="org.example",
        artifact_id="demo",
        package_name="org.example:demo",
        version=version,
    )


def _scan(stderr: str, *, findings: tuple[VulnerabilityFinding, ...] = ()) -> ScanReport:
    return ScanReport(
        succeeded=True,
        findings=findings,
        command_result=CommandResult(
            command=["osv-scanner"],
            cwd="/repo",
            exit_code=0,
            stderr=stderr,
        ),
        raw_report_path="/tmp/osv.json",
        outcome=ScanOutcome.COMPLETED_WITH_FINDINGS if findings else ScanOutcome.COMPLETED_CLEAN,
        backend="osv",
    )


BASELINE_STDERR = """
Scanned /repo/pom.xml file and found 4 packages
Scanned /repo/service/pom.xml file and found 6 packages
Scanned /repo/web/pom.xml file and found 6 packages
Filtered 6 local/unscannable package/s from the scan.
"""

COMPARABLE_STDERR = """
Scanned /repo/pom.xml file and found 4 packages
Scanned /repo/service/pom.xml file and found 6 packages
Scanned /repo/web/pom.xml file and found 6 packages
Filtered 6 local/unscannable package/s from the scan.
"""

REGRESSED_STDERR = """
Scanned /repo/pom.xml file and found 0 packages
Scanned /repo/service/pom.xml file and found 2 packages
Scanned /repo/web/pom.xml file and found 4 packages
Filtered 6 local/unscannable package/s from the scan.
"""


def test_comparable_osv_coverage_allows_resolution_comparison() -> None:
    complete, reason, evidence = _target_comparison_coverage(
        _scan(BASELINE_STDERR),
        _scan(COMPARABLE_STDERR),
        build_passed=True,
    )

    assert complete is True
    assert reason is None
    assert evidence["baseline"]["scannablePackages"] == 10
    assert evidence["current"]["scannablePackages"] == 10


def test_regressed_osv_coverage_fails_closed() -> None:
    complete, reason, evidence = _target_comparison_coverage(
        _scan(BASELINE_STDERR),
        _scan(REGRESSED_STDERR),
        build_passed=True,
    )

    assert complete is False
    assert reason is not None
    assert "coverage regressed" in reason
    assert evidence["current"]["scannablePackages"] == 0


def test_failed_build_makes_scan_comparison_non_authoritative() -> None:
    complete, reason, _ = _target_comparison_coverage(
        _scan(BASELINE_STDERR),
        _scan(COMPARABLE_STDERR),
        build_passed=False,
    )

    assert complete is False
    assert reason is not None
    assert "build/test validation failed" in reason


def test_absent_target_is_unknown_when_comparison_is_incomplete() -> None:
    target = _finding()

    resolved, remaining, unknown = _classify_target_findings(
        (target,),
        (),
        comparison_complete=False,
    )

    assert resolved == []
    assert remaining == []
    assert [item["identity"] for item in unknown] == [target.identity]


def test_visible_target_remains_remaining_even_when_coverage_is_incomplete() -> None:
    target = _finding()

    resolved, remaining, unknown = _classify_target_findings(
        (target,),
        (_finding("1.1"),),
        comparison_complete=False,
    )

    assert resolved == []
    assert [item["identity"] for item in remaining] == [target.identity]
    assert unknown == []


def test_absent_target_is_resolved_only_with_complete_comparison() -> None:
    target = _finding()

    resolved, remaining, unknown = _classify_target_findings(
        (target,),
        (),
        comparison_complete=True,
    )

    assert [item["identity"] for item in resolved] == [target.identity]
    assert remaining == []
    assert unknown == []
