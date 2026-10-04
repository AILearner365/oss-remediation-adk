"""Offline request-path diagnostics; no model reasoning or live recovery claim."""
import asyncio
import json
import unittest

from scripts.inspect_intent_interface import inspect_variant, compact_evidence, ROOT


class UnknownToolInterfaceTests(unittest.TestCase):
    def test_both_provider_conversions_preserve_declaration_and_deliver_feedback(self):
        prior = json.loads((ROOT / 'docs/verification/intent-shape-20261003/intent-tool-declaration.json').read_text())
        declarations = []
        for vertex in (False, True):
            with self.subTest(vertex=vertex):
                result = asyncio.run(inspect_variant(vertex))
                self.assertTrue(result['passed'], result['checks'])
                compact = compact_evidence(result)
                for raw, saved in zip(result['requests'], compact['requests']):
                    self.assertEqual(raw['correctionResponses'],
                                     [compact['feedbackByAttempt'][key] for key in saved['correctionAttempts']])
                    self.assertEqual(raw['continuationMessages'],
                                     [compact['continuationBySha256'][key] for key in saved['continuationSha256']])
                declaration = result['providerIntentDeclaration']
                declarations.append(declaration)
                self.assertEqual(prior, declaration)
                schema = declaration['parameters_json_schema']
                self.assertEqual(['cycle_number', 'answers'], schema['required'])
                self.assertEqual('#/$defs/IntentAnswer', schema['properties']['answers']['items']['$ref'])
                self.assertEqual(['section', 'answer'], schema['$defs']['IntentAnswer']['required'])
                for request in result['requests']:
                    self.assertEqual(1, request['callableNames'].count('submit_cycle_intent'))
                    self.assertNotIn('SubmitCycleIntentAnswers', request['callableNames'])
                    self.assertNotIn('SubmitCycleIntentAnswersEvidence', request['callableNames'])
                    self.assertNotIn('google:python_interpreter', request['callableNames'])
                self.assertIn('not callable tools', result['requests'][2]['continuationMessages'][-1])
        self.assertEqual(declarations[0], declarations[1])
