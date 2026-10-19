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
                conn.execute('CREATE TABLE tasks (task_id TEXT PRIMARY KEY, request_json TEXT, status TEXT, accepted INTEGER, validation_status TEXT)')
                conn.execute('INSERT INTO tasks VALUES (?, ?, ?, ?, ?)',
                             (details['taskId'], json.dumps({'delivery': {'mode': 'github_pr'}}),
                              'ACCEPTED', 1, 'PASSED'))
            delivery.claim_delivery(db, details)
            with self.assertRaisesRegex(ValueError, 'already claimed'):
                delivery.claim_delivery(db, details)
            delivery.record_delivery(db, details['taskId'], 'https://github.com/example/pr/1', 'd' * 40)
            with self.assertRaisesRegex(ValueError, 'already completed'):
                delivery.record_delivery(db, details['taskId'], 'https://github.com/example/pr/2', 'e' * 40)
            with sqlite3.connect(db) as conn:
                status, url = conn.execute('SELECT state, pr_url FROM openhands_delivery_claims').fetchone()
            self.assertEqual(status, 'PR_CREATED')
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
