"""Deterministic review outcome and real subprocess exit-code regressions."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from google.auth.exceptions import DefaultCredentialsError
from autonomous_oss_remediation_agent.workspace import RunWorkspace
from scripts.reasoning_boundary_scenarios import prepare_decision, retain_review, run_decision
from scripts.intent_recovery_scenarios import seed_answers
from tests.unit.test_intent_tool_recovery import _ScriptedModel

ROOT = Path(__file__).resolve().parents[2]
HISTORICAL = ROOT / 'autonomous-oss-remediation-workspaces/run-20261003T191038Z-e662889c/artifacts'
REVIEW = ROOT / 'docs/verification/reasoning-boundaries-20261003/coverage-review.json'


class DecisionReviewReportingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name) / 'run'
        self.artifacts = self.workspace / 'artifacts'
        for name in ('acceptance-result.json', 'fixture/accepted-decision.json', 'agent/decision-journal.md'):
            dest = self.artifacts / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(HISTORICAL / name, dest)
        self.raw = json.loads((self.artifacts / 'acceptance-result.json').read_text())
        self.review = json.loads(REVIEW.read_text())
        for criterion in self.review['criteria'].values():
            criterion['status'] = 'PASSED'  # Synthetic reviewer decision, not a revision of historical truth.

    def write_raw(self):
        (self.artifacts / 'acceptance-result.json').write_text(json.dumps(self.raw))

    def test_successful_execution_and_semantic_pass(self):
        before = (self.artifacts / 'acceptance-result.json').read_bytes()
        reviewed = retain_review(self.workspace, self.review)
        self.assertEqual(('PASSED', 'PASSED', 'PASSED', 'PASSED'),
                         tuple(reviewed[k] for k in ('capture', 'execution', 'semanticAssessment', 'outcome')))
        self.assertTrue(reviewed['passed'])
        self.assertEqual(before, (self.artifacts / 'acceptance-result.json').read_bytes())
        with self.assertRaises(FileExistsError):
            retain_review(self.workspace, self.review)
        with self.assertRaises(FileExistsError):
            retain_review(self.workspace, self.review, output=self.artifacts / 'acceptance-result.json')

    def test_successful_execution_and_semantic_failure(self):
        self.review['criteria']['cited_support']['status'] = 'FAILED'
        reviewed = retain_review(self.workspace, self.review)
        self.assertEqual('PASSED', reviewed['execution'])
        self.assertEqual('FAILED', reviewed['semanticAssessment'])
        self.assertEqual('FAILED', reviewed['outcome'])
        self.assertFalse(reviewed['passed'])

    def test_legacy_failed_capture_and_terminal_error_cannot_be_erased(self):
        self.raw.update(capture='FAILED', outcome='FAILED', terminalError='RuntimeError: after acceptance')
        self.write_raw()
        reviewed = retain_review(self.workspace, self.review)
        self.assertEqual('FAILED', reviewed['capture'])
        self.assertEqual('FAILED', reviewed['execution'])
        self.assertEqual('PASSED', reviewed['semanticAssessment'])
        self.assertEqual('FAILED', reviewed['outcome'])
        self.assertEqual(self.raw['terminalError'], reviewed['terminalError'])
        self.assertFalse(reviewed['passed'])

    def test_real_adk_accepted_record_then_failure_or_blockage(self):
        for error in (RuntimeError('after acceptance'), DefaultCredentialsError('provider unavailable')):
            with self.subTest(error=type(error).__name__):
                f = prepare_decision(RunWorkspace.create(self.temp.name), 'finding-coverage')
                def fail_after_acceptance():
                    if f.lifecycle.cycles[1].intent is not None:
                        raise error
                model = _ScriptedModel([('submit_cycle_intent', {'cycle_number': 1,
                    'answers': seed_answers(f.evidence['supportReference'])})], inspect=fail_after_acceptance)
                with patch('autonomous_oss_remediation_agent.agent.Gemini', return_value=model):
                    raw = asyncio.run(run_decision(f, 'scripted'))
                expected = 'BLOCKED' if isinstance(error, DefaultCredentialsError) else 'FAILED'
                self.assertTrue(raw['acceptedRecordVerified'])
                self.assertEqual('PASSED', raw['capture'])
                self.assertEqual(expected, raw['execution'])
                self.assertEqual(expected, raw['outcome'])
                raw['scenario'] = f.case
                (f.trace.workspace.artifacts / 'acceptance-result.json').write_text(json.dumps(raw))
                review = deepcopy(self.review)
                review.update(acceptedContentHash=raw['acceptedContentHash'], selectedCandidateId=raw['selectedCandidate']['id'])
                result = retain_review(f.trace.workspace.root, review)
                self.assertEqual('PASSED', result['semanticAssessment'])
                self.assertEqual(expected, result['outcome'])
                self.assertFalse(result['passed'])

    def test_pending_or_unexercised_review_never_passes(self):
        for state in ('PENDING', 'NOT_EXERCISED'):
            with self.subTest(state=state):
                self.review['criteria']['cited_support']['status'] = state
                result = retain_review(self.workspace, self.review, output=Path(self.temp.name) / (state + '.json'))
                self.assertEqual('PASSED', result['execution'])
                self.assertEqual(state, result['semanticAssessment'])
                self.assertEqual('NOT_EXERCISED', result['outcome'])
                self.assertFalse(result['passed'])
        del self.review['criteria']['cited_support']
        with self.assertRaisesRegex(ValueError, 'every scenario criterion'):
            retain_review(self.workspace, self.review)

    def test_inconsistent_success_flag_does_not_hide_terminal_error(self):
        self.raw.update(execution='PASSED', terminalError='RuntimeError: close failed')
        self.write_raw()
        self.assertEqual('FAILED', retain_review(self.workspace, self.review)['outcome'])

    def test_unexercised_execution_cannot_be_promoted_by_semantic_pass(self):
        self.raw.update(execution='NOT_EXERCISED')
        self.write_raw()
        result = retain_review(self.workspace, self.review)
        self.assertEqual('PASSED', result['semanticAssessment'])
        self.assertEqual('NOT_EXERCISED', result['outcome'])
        self.assertFalse(result['passed'])

    def test_offline_preparation_cli_is_not_an_overall_pass(self):
        process = subprocess.run([sys.executable, '-m', 'scripts.retained_evidence_acceptance',
            '--scenario', 'finding-coverage', '--workspace-parent', str(Path(self.temp.name) / 'preparation')],
            cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(1, process.returncode, process.stderr)
        result = json.loads(process.stdout)['trials'][0]
        self.assertEqual('PASSED', result['offlineMechanics'])
        self.assertEqual('NOT_EXERCISED', result['execution'])
        self.assertEqual('NOT_EXERCISED', result['outcome'])
        self.assertFalse(result['passed'])

    def test_actual_cli_exit_codes(self):
        original = deepcopy(self.raw)
        for status in ('PASSED', 'FAILED', 'BLOCKED', 'PENDING', 'NOT_EXERCISED'):
            with self.subTest(status=status):
                self.raw = deepcopy(original)
                for criterion in self.review['criteria'].values():
                    criterion['status'] = 'PASSED'
                if status == 'BLOCKED':
                    self.raw.update(outcome='BLOCKED', terminalError='DefaultCredentialsError: unavailable')
                else:
                    self.review['criteria']['cited_support']['status'] = status
                self.write_raw()
                review_path = Path(self.temp.name) / 'review.json'
                review_path.write_text(json.dumps(self.review))
                output = Path(self.temp.name) / (status + '.json')
                process = subprocess.run([sys.executable, '-m', 'scripts.reasoning_boundary_scenarios',
                    '--workspace', str(self.workspace), '--review', str(review_path), '--output', str(output)],
                    cwd=ROOT, capture_output=True, text=True, timeout=60)
                self.assertEqual(0 if status == 'PASSED' else 1, process.returncode, process.stderr)
                result = json.loads(process.stdout)
                self.assertEqual('NOT_EXERCISED' if status == 'PENDING' else status, result['outcome'])
                self.assertEqual(result, json.loads(output.read_text()))
