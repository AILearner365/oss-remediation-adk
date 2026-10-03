"""Offline scenario plumbing: scripted calls are never live reasoning evidence."""
import asyncio
import json
from copy import deepcopy
import tempfile
import unittest
from unittest.mock import patch

from google.auth.exceptions import DefaultCredentialsError
from autonomous_oss_remediation_agent.workspace import RunWorkspace
from scripts.reasoning_boundary_scenarios import CASES, REVIEW_CRITERIA, prepare_decision, run_decision, score_decision, retain_review
from scripts.intent_recovery_scenarios import seed_answers
from tests.unit.test_intent_tool_recovery import _ScriptedModel


class ReasoningBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def fixture(self, case):
        return prepare_decision(RunWorkspace.create(self.temp.name), case)

    def test_coverage_input_uses_all_findings_without_seeding_intent(self):
        f = self.fixture(CASES[0])
        for label in ('A', 'B', 'C'):
            self.assertIn('FINDING-' + label, f.message)
        self.assertIn('2.4.5', f.message)
        self.assertIn('2.4.2', f.message)
        self.assertEqual(0, f.lifecycle.cycles[1].intent_attempts)
        self.assertIsNone(f.lifecycle.cycles[1].intent)
        self.assertEqual('NOT_EXERCISED', score_decision(f)['outcome'])

    def test_blocked_and_authoritative_evidence_are_both_supplied_via_capability(self):
        f = self.fixture(CASES[1])
        blocked, official = f.evidence['research_search'], f.evidence['research_fetch']
        self.assertEqual('blocked', blocked['status'])
        self.assertEqual('BOT_CHALLENGE', blocked['failure_code'])
        self.assertFalse(blocked['extractionSucceeded'])
        self.assertEqual('success', official['status'])
        self.assertIn('availability only', official['content'])
        self.assertIn('probably custom', f.message)
        self.assertIn(official['content'], f.message.replace('\\n', '\n'))
        self.assertEqual(2, f.budget.tool_calls)
        self.assertEqual(0, f.lifecycle.cycles[1].intent_attempts)
        self.assertIn('controlled_evidence_acquisition', f.trace.events_path.read_text())
        self.assertNotIn('adk_interaction', f.trace.events_path.read_text())

    def test_real_adk_capture_does_not_pass_wrong_decision_and_ignores_later_call(self):
        f = self.fixture(CASES[0])
        # Deliberately unrelated decision: verifies that capture never becomes a reasoning pass.
        answers = seed_answers(f.evidence['supportReference'])
        model = _ScriptedModel([('submit_cycle_intent', {'cycle_number': 1, 'answers': answers}), 'Done'])
        with patch('autonomous_oss_remediation_agent.agent.Gemini', return_value=model):
            result = asyncio.run(run_decision(f, 'scripted'))
        self.assertTrue(result['acceptedRecordVerified'])
        self.assertEqual('PASSED', result['capture'])
        self.assertEqual('PENDING', result['decisionReview'])
        self.assertEqual('NOT_EXERCISED', result['outcome'])
        self.assertFalse(result['passed'])
        result['scenario'] = CASES[0]
        (f.trace.workspace.artifacts / 'acceptance-result.json').write_text(json.dumps(result))
        review = {'acceptedContentHash': result['acceptedContentHash'],
                  'selectedCandidateId': result['selectedCandidate']['id'],
                  'criteria': {name: {'status': 'PASSED', 'rationale': 'Test review only',
                                      'evidence': ['fixture/accepted-decision.json']}
                               for name in REVIEW_CRITERIA[CASES[0]]}}
        review['criteria']['selected_solution_coverage']['status'] = 'FAILED'
        reviewed = retain_review(f.trace.workspace.root, review)
        self.assertEqual('FAILED', reviewed['outcome'])
        self.assertFalse(reviewed['passed'])
        missing = deepcopy(review)
        del missing['criteria']['all_findings']
        with self.assertRaises(ValueError):
            retain_review(f.trace.workspace.root, missing)
        wrong = deepcopy(review)
        wrong['selectedCandidateId'] = 'not_selected'
        with self.assertRaises(ValueError):
            retain_review(f.trace.workspace.root, wrong)
        wrong = deepcopy(review)
        wrong['acceptedContentHash'] = 'wrong'
        with self.assertRaises(ValueError):
            retain_review(f.trace.workspace.root, wrong)
        exported_path = f.trace.workspace.artifacts / 'fixture/accepted-decision.json'
        original_export = exported_path.read_text()
        altered = json.loads(original_export)
        altered['selectedCandidate']['solution'] = 'Tampered export'
        exported_path.write_text(json.dumps(altered))
        with self.assertRaises(ValueError):
            retain_review(f.trace.workspace.root, review)
        exported_path.write_text(original_export)
        changed = deepcopy(answers)
        changed[3]['candidates'][0]['solution'] = 'Later unsupported claim'
        f.trace.append_event('adk_interaction', interactionType='tool_call', cycle=1,
                             name='submit_cycle_intent', arguments={'cycle_number': 1, 'answers': changed})
        self.assertNotEqual('Later unsupported claim', score_decision(f, live=True)['selectedCandidate']['solution'])
        f.lifecycle.store.path.write_bytes(f.lifecycle.store.path.read_bytes().replace(b'Stream adapter', b'Broken adapter'))
        with self.assertRaises(ValueError):
            retain_review(f.trace.workspace.root, review)
        self.assertFalse(score_decision(f, live=True)['acceptedRecordVerified'])
        self.assertEqual('FAILED', score_decision(f, live=True)['outcome'])

    def test_credentials_block_is_not_model_failure(self):
        f = self.fixture(CASES[1])
        with patch('scripts.reasoning_boundary_scenarios.default_agent_session_factory', side_effect=DefaultCredentialsError('unavailable')):
            result = asyncio.run(run_decision(f, 'scripted'))
        self.assertEqual('BLOCKED', result['outcome'])
        self.assertEqual('NOT_EXERCISED', result['decisionReview'])
        self.assertFalse(result['passed'])
