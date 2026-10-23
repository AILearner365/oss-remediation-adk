"""Scanner replacement and shared comparison; no network/model/delivery."""
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from native_remediation import scanners, validation
from native_remediation.contract import load_task
from native_remediation.files import Blocked, digest, write
from tests_native.test_product import evaluation, task_input, GitFixture


class FrozenScanner:
    """A second adapter needs no returned clean-package inventory or SBOM."""
    def scan(self, request):
        write(request.directory / 'frozen.json', {'assessment': 'complete'})
        return dict(status='COMPLETE', findings=[], evidence=['frozen.json'],
            coverage=dict(complete=True, inputDigest=digest(request.packages), evidence=['frozen.json']))


class ScannerContractTests(unittest.TestCase):
    def test_runtime_selection_and_scoped_attestation_without_clean_inventory(self):
        with patch.dict(scanners.SCANNERS, frozen=FrozenScanner), tempfile.TemporaryDirectory() as directory:
            task = load_task(dict(task_input(), scanner={'type': 'frozen', 'version': 'fixture-1', 'options': {}}))
            packages = [dict(name='g:a', version='1')]
            request = scanners.ScanRequest(packages, Path(directory), Path(directory), task['scanner'], {}, None)
            result = scanners.scanner(task['scanner']).scan(request)
            scanners.validate_result(result, packages)
            record = dict(result, scanner=task['scanner'], inventory=dict(packages=packages))
            self.assertTrue(scanners.complete_coverage(record))
            record['inventory']['packages'] = [dict(name='g:b', version='1')]
            self.assertFalse(scanners.complete_coverage(record))
        with self.assertRaises(Blocked):
            load_task(dict(task_input(), scanner={'type': 'not-installed'}))

    def test_osv_input_preserves_namespace_and_purl(self):
        packages = [dict(name='one:shared', version='1'), dict(name='two:shared', version='1')]
        bom = scanners.sbom(packages)
        self.assertEqual([c['name'] for c in bom['components']], ['one:shared', 'two:shared'])
        self.assertEqual(bom['components'][0]['purl'], 'pkg:maven/one/shared@1')
        rows = [dict(package=dict(p, ecosystem='Maven')) for p in packages]
        result = scanners.normalize_osv(dict(results=[dict(packages=rows)]), packages, 0, '')
        self.assertTrue(result['coverage']['complete'])
        rows[0]['package']['name'] = 'shared'
        with self.assertRaisesRegex(Blocked, 'identity'):
            scanners.normalize_osv(dict(results=[dict(packages=rows)]), packages, 0, '')

    def test_result_contract_malformed_incomplete_and_ambiguous(self):
        packages = [dict(name='g:a', version='1')]
        for result in ({}, dict(status='COMPLETE', findings=[], coverage={}, evidence=[]),
                dict(status='COMPLETE', findings=[dict(package='a', version='1', ids=['CVE-1'])], coverage={}, evidence=['raw'])):
            with self.subTest(result=result), self.assertRaises(Blocked):
                scanners.validate_result(result, packages)
        incomplete = dict(status='INCONCLUSIVE', findings=[], coverage=dict(complete=False), evidence=['raw'])
        scanners.validate_result(incomplete, packages)
        self.assertFalse(scanners.complete_coverage(dict(incomplete, inventory=dict(packages=packages))))


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_task(task_input())['policy']
        self.old, self.new = evaluation('base', True), evaluation('candidate')

    def report(self):
        report = validation.compare(self.old, self.new, self.policy)
        for category, rows in report['vulnerabilities'].items():
            self.assertEqual(report['summary'][category], len(rows))
        self.assertEqual(report['candidateDigest'], digest(self.new))
        self.assertEqual(report['baselineDigest'], digest(self.old))
        return report

    def test_resolved_with_candidate_versions_paths_and_actual_details(self):
        report = self.report()
        self.assertEqual(report['outcome'], 'PASS')
        finding = report['vulnerabilities']['resolved'][0]
        self.assertEqual(finding['candidateDependencyVersions'], ['1.0.1'])
        self.assertTrue(finding['dependencyPaths']['baseline'])
        self.assertEqual(finding['baselineFindings'], self.old['findings'])

    def test_version_change_does_not_make_persistent_advisory_introduced(self):
        self.new['findings'] = [dict(self.old['findings'][0], version='1.0.1', ids=['CVE-test'])]
        report = self.report()
        self.assertEqual(report['summary']['remaining'], 1)
        self.assertEqual(report['summary']['introduced'], 0)
        self.assertEqual(report['outcome'], 'FAIL')

    def test_transitive_aliases_deduplicate_and_new_finding_is_separate(self):
        self.old['findings'] += [dict(self.old['findings'][0], ids=['GHSA-test', 'OSV-test'])]
        self.new['findings'] = [dict(self.old['findings'][0], version='1.0.1', ids=['OSV-test']),
            dict(self.old['findings'][0], version='1.0.1', ids=['NEW-test'])]
        report = self.report()
        self.assertEqual(report['summary']['baseline'], 1)
        self.assertEqual(report['summary']['remaining'], 1)
        self.assertEqual(report['summary']['introduced'], 1)

    def test_missing_scan_never_resolves_and_policy_failure_remains_visible(self):
        self.new.update(outcome='INCONCLUSIVE', coverage=dict(complete=False))
        self.new.pop('findings')
        report = self.report()
        self.assertEqual(report['summary']['resolved'], 0)
        self.assertEqual(report['summary']['unknown'], 1)
        self.assertEqual(report['outcome'], 'INCONCLUSIVE')
        self.new['inventory']['properties']['app:root']['java.version'] = '22'
        report = self.report()
        self.assertEqual(report['outcome'], 'FAIL')
        self.assertEqual(report['checks']['javaPolicy'], 'FAIL')
        self.assertEqual(report['checks']['scanCoverage'], 'INCONCLUSIVE')


    def test_invalid_identity_and_changed_scanner_configuration_unknown(self):
        self.new['findings'] = [dict(package='library', version='1.0.1', ids=['CVE-test'])]
        self.assertNotEqual(self.report()['outcome'], 'PASS')
        self.new['findings'] = []
        self.new['scanner'] = dict(type='frozen', version='1')
        self.assertEqual(self.report()['summary']['resolved'], 0)

    def test_build_failure_and_incomplete_scan_retained_together(self):
        self.new.update(outcome='FAIL', reasons=['build failed'], coverage=dict(complete=False),
            commands=[dict(name='build', exitCode=1, timedOut=False)])
        report = self.report()
        self.assertEqual(report['outcome'], 'FAIL')
        self.assertEqual(report['checks']['build'], 'FAIL')
        self.assertEqual(report['checks']['scanCoverage'], 'INCONCLUSIVE')


class ReplacementPipelineTests(GitFixture):
    def test_second_adapter_runs_existing_maven_validator_without_osv_or_sbom(self):
        def runner(argv, source, timeout, output):
            self.assertNotIn('scan', argv)
            target = source / 'target'
            target.mkdir(exist_ok=True)
            if 'clean' in argv:
                reports = target / 'surefire-reports'
                reports.mkdir()
                (reports / 'TEST-fixture.xml').write_text('<testsuite tests="2"/>')
            else:
                write(target / validation.TREE_FILE, self.baseline['inventory']['graphs'][0]['graph'])
                (target / 'effective-pom.xml').write_text('<project><groupId>app</groupId><artifactId>root</artifactId><version>1</version><properties><java.version>21</java.version></properties></project>')
            record = dict(exitCode=0, timedOut=False, stdout='', stderr='')
            write(output, record)
            return record
        with patch.dict(scanners.SCANNERS, frozen=FrozenScanner):
            task = load_task(dict(self.task, scanner=dict(type='frozen', version='1')))
            directory = self.state / 'frozen-evaluation'
            result = validation.evaluate(self.workspace, self.baseline['tree'], task, directory,
                deadline=time.time() + 30, runner=runner)
            self.assertEqual(result['outcome'], 'COMPLETE', result)
            self.assertFalse((directory / 'bom.cdx.json').exists())
            validation.require_baseline(result, self.baseline['tree'], task)
            self.assertEqual(validation.compare(result, result, task['policy'])['outcome'], 'PASS')



if __name__ == '__main__':
    unittest.main()
