import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import openhands_pr_delivery as delivery

class DeliveryLedgerTests(unittest.TestCase):
    def test_irreversible_claim_and_result(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / 'tasks.sqlite3'
            details = {'taskId': 'task_' + 'a' * 32, 'baseCommit': 'b' * 40,
                       'validatedTree': 'c' * 40, 'branch': 'openhands/remediate-task-' + 'a' * 32}
            with sqlite3.connect(db) as conn:
                conn.execute('CREATE TABLE tasks (task_id TEXT PRIMARY KEY, request_json TEXT, status TEXT, stage TEXT, accepted INTEGER, validation_status TEXT, delivery_status TEXT, result_json TEXT, updated_at TEXT, execution_status TEXT)')
                conn.execute('INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                             (details['taskId'], json.dumps({'delivery': {'mode': 'github_pr'}}),
                              'ACCEPTED', 'accepted', 1, 'PASSED', 'PENDING', None, '', 'COMPLETED'))
            delivery.claim_delivery(db, details)
            with self.assertRaisesRegex(ValueError, 'already claimed'):
                delivery.claim_delivery(db, details)
            with sqlite3.connect(db) as conn:
                conn.execute('CREATE TABLE validation_attempts (task_id TEXT, attempt INTEGER, validated_tree TEXT, report_artifact_id TEXT, state TEXT, outcome TEXT)')
                conn.execute('INSERT INTO validation_attempts VALUES (?, 1, ?, ?, ?, ?)',
                             (details['taskId'], 'c'*40, 'validation-report', 'COMPLETED', 'PASS'))
                conn.execute('CREATE TABLE openhands_runtimes (task_id TEXT, baseline_commit TEXT, conversation_id TEXT)')
                conn.execute('INSERT INTO openhands_runtimes VALUES (?, ?, ?)', (details['taskId'], 'b'*40, 'conv-123'))
                conn.execute('CREATE TABLE artifacts (task_id TEXT, artifact_id TEXT, created_at TEXT)')
            delivery.record_delivery(db, details['taskId'], 'https://github.com/example/pr/1', 'd' * 40)
            with self.assertRaisesRegex(ValueError, 'already completed'):
                delivery.record_delivery(db, details['taskId'], 'https://github.com/example/pr/2', 'e' * 40)
            with sqlite3.connect(db) as conn:
                status, url = conn.execute('SELECT state, pr_url FROM openhands_delivery_claims').fetchone()
            self.assertEqual(status, 'PR_CREATED')
            with sqlite3.connect(db) as conn:
                self.assertEqual(conn.execute('SELECT status FROM tasks').fetchone()[0], 'SUCCEEDED')
            self.assertEqual(url, 'https://github.com/example/pr/1')

    def test_none_mode_never_claims(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / 'tasks.sqlite3'
            tid = 'task_' + 'b' * 32
            with sqlite3.connect(db) as conn:
                conn.execute('CREATE TABLE tasks (task_id TEXT PRIMARY KEY, request_json TEXT, status TEXT, accepted INTEGER, validation_status TEXT)')
                conn.execute('INSERT INTO tasks VALUES (?, ?, ?, ?, ?)',
                             (tid, json.dumps({'delivery': {'mode': 'none'}}), 'ACCEPTED', 1, 'PASSED'))
            with self.assertRaisesRegex(ValueError, 'does not authorize'):
                delivery.claim_delivery(db, {'taskId':tid, 'baseCommit':'a'*40, 'validatedTree':'b'*40, 'branch':'test'})

if __name__ == '__main__':
    unittest.main()
