"""Small scanner boundary. Maven, comparison, policy and acceptance live elsewhere.

Adapters attest coverage of the supplied resolved scope, with original evidence.
They need not return an inventory of non-vulnerable packages. Register trusted
implementations here; task data never imports code or supplies arbitrary flags.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Callable, Protocol
from urllib.parse import quote

from .files import Blocked, digest, write


@dataclass(frozen=True)
class ScanRequest:
    packages: list
    source: Path
    directory: Path
    config: dict
    tools: dict
    run: Callable


class VulnerabilityScanner(Protocol):
    def scan(self, request: ScanRequest) -> dict:
        """Return status, findings, coverage and original evidence references."""
        ...


def sbom(packages):
    components = []
    for package in packages:
        group, artifact = package['name'].split(':', 1)
        purl = 'pkg:maven/' + quote(group, safe='') + '/' + quote(artifact, safe='') + '@' + quote(package['version'], safe='')
        # OSV 2.6 serializes CDX component.name, NOT its group or PURL. Use the
        # canonical coordinate as display name too; never infer a namespace from
        # artifact-only output. The PURL remains the authoritative query input.
        components.append(dict(type='library', name=package['name'],
            version=package['version'], purl=purl, **{'bom-ref': purl}))
    return dict(bomFormat='CycloneDX', specVersion='1.5', version=1, components=components)


def normalize_osv(payload, packages, exit_code, stderr):
    if (exit_code not in (0, 1) or not isinstance(payload, dict)
            or not isinstance(payload.get('results'), list)
            or re.search(r'\b(error|failed|unscannable|filtered)\b', stderr, re.I)):
        raise Blocked('OSV error/incomplete extraction; absence of findings is not PASS')
    expected = {(p['name'], p['version']) for p in packages}
    covered, findings = set(), []
    for source in payload['results']:
        if not isinstance(source, dict) or not isinstance(source.get('packages'), list):
            raise Blocked('OSV package coverage missing')
        for index, row in enumerate(source['packages']):
            if not isinstance(row, dict) or not isinstance(row.get('package'), dict):
                raise Blocked('Malformed OSV package record')
            package = row.get('package', {})
            key = (package.get('name'), package.get('version'))
            if package.get('ecosystem') != 'Maven' or key not in expected:
                raise Blocked('Unexpected OSV package identity')
            covered.add(key)
            vulnerabilities = row.get('vulnerabilities', [])
            if not isinstance(vulnerabilities, list):
                raise Blocked('Malformed vulnerability coverage')
            for vuln in vulnerabilities:
                if not isinstance(vuln, dict) or not isinstance(vuln.get('id'), str) or not vuln['id']:
                    raise Blocked('Malformed OSV finding')
                aliases = vuln.get('aliases', [])
                if not isinstance(aliases, list) or not all(isinstance(v, str) and v for v in aliases):
                    raise Blocked('Malformed OSV aliases')
                affected_rows = vuln.get('affected', [])
                if (not isinstance(affected_rows, list) or any(not isinstance(a, dict)
                        or not isinstance(a.get('package', {}), dict) or not isinstance(a.get('ranges', []), list)
                        or any(not isinstance(r, dict) or not isinstance(r.get('events', []), list)
                            or any(not isinstance(e, dict) for e in r.get('events', []))
                            for r in a.get('ranges', [])) for a in affected_rows)):
                    raise Blocked('Malformed OSV affected/fix evidence')
                findings.append(dict(package=key[0], version=key[1], ids=sorted({vuln['id'], *aliases}),
                    summary=vuln.get('summary', ''), affected=vuln.get('affected', []),
                    fixedVersions=sorted({event['fixed'] for affected in vuln.get('affected', [])
                        if affected.get('package', {}).get('name') == key[0]
                        and affected.get('package', {}).get('ecosystem') == 'Maven'
                        for interval in affected.get('ranges', []) for event in interval.get('events', [])
                        if isinstance(event.get('fixed'), str)}),
                    severity=vuln.get('severity', []), databaseSpecific=vuln.get('database_specific', {}),
                    references=vuln.get('references', []), sourceEvidence=['scan.json'],
                    sourcePackageIndex=index))
    if covered != expected or bool(findings) != (exit_code == 1):
        raise Blocked('OSV exit/report disagreement or incomplete resolved-package coverage')
    return dict(status='COMPLETE', coverage=dict(expected=len(expected), scanned=len(covered), complete=True,
        inputDigest=digest(packages), evidence=['bom.cdx.json', 'scan.json'],
        scope='Resolved Maven project dependency graphs, all scopes; excludes build-plugin/JDK/OS dependencies'),
        findings=findings, evidence=['scanner-version.json', 'bom.cdx.json', 'scan.json'])


class OsvScanner:
    def validate_config(self, config):
        if config['version'] != '2.6.0' or config.get('options'):
            raise Blocked('OSV 2.6.0 with trusted scan flags is required')

    def scan(self, request):
        self.validate_config(request.config)
        directory, run = request.directory, request.run
        write(directory / 'bom.cdx.json', sbom(request.packages))
        config = directory / 'osv-scanner.toml'
        config.write_text('# Trusted validator: no vulnerability ignore entries.\n')
        version = run([request.tools['osv'], '--version'], 'scanner-version')
        if version['exitCode'] or not re.search(r'osv-scanner version: 2\.6\.0\b', version['stdout']):
            raise Blocked('OSV 2.6.0 required for the verified CLI contract')
        scan = run([request.tools['osv'], 'scan', 'source', '--sbom=' + str(directory / 'bom.cdx.json'),
            '--format=json', '--all-packages', '--all-vulns', '--config=' + str(config)], 'scan')
        return normalize_osv(json.loads(scan['stdout']), request.packages, scan['exitCode'], scan['stderr'])


SCANNERS = {'osv': OsvScanner}


def scanner(config):
    try:
        implementation = SCANNERS[config['type']]()
        if hasattr(implementation, 'validate_config'):
            implementation.validate_config(config)
        return implementation
    except (KeyError, TypeError):
        raise Blocked('Unknown scanner adapter') from None


def complete_coverage(evaluation):
    coverage = evaluation.get('coverage', {})
    packages = evaluation.get('inventory', {}).get('packages', [])
    if (not packages or coverage.get('complete') is not True
            or evaluation.get('status', 'COMPLETE') != 'COMPLETE'):
        return False
    if 'inputDigest' in coverage:
        return coverage['inputDigest'] == digest(packages) and bool(coverage.get('evidence'))
    if 'scanner' in evaluation:
        return False
    # Retained pre-interface records: these required an exact returned inventory.
    count = len({(p['name'], p['version']) for p in packages})
    return (type(coverage.get('expected')) is int and type(coverage.get('scanned')) is int
        and coverage['expected'] == coverage['scanned'] == count)


def validate_result(result, packages):
    """Fail closed on an adapter violating the shared result contract."""
    expected = {(p['name'], p['version']) for p in packages}
    if (not isinstance(result, dict) or result.get('status') not in ('COMPLETE', 'INCONCLUSIVE', 'FAILED')
            or not isinstance(result.get('findings'), list) or not isinstance(result.get('coverage'), dict)
            or not isinstance(result.get('evidence'), list) or not result['evidence']):
        raise Blocked('Malformed scanner result contract')
    for finding in result['findings']:
        if (not isinstance(finding, dict) or (finding.get('package'), finding.get('version')) not in expected
                or not isinstance(finding.get('ids'), list) or not finding['ids']
                or not all(isinstance(v, str) and v for v in finding['ids'])):
            raise Blocked('Ambiguous scanner finding identity')
    if result['coverage'].get('complete') is True and result['status'] != 'COMPLETE':
        raise Blocked('Scanner status/coverage disagreement')
