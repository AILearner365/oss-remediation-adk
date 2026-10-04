"""Offline ADK/GenAI wire diagnostic: historical model calls, intercepted transport.

No credentials are loaded, no provider request is sent, and no Intent is supplied.
The existing scenario setup, agent, callback and continuation loop are reused.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from google import genai
from google.auth.credentials import AnonymousCredentials
from google.genai import types

from autonomous_oss_remediation_agent.agent import default_agent_session_factory, IntentToolRecoveryExhausted
from autonomous_oss_remediation_agent.workspace import RunWorkspace
from scripts.reasoning_boundary_scenarios import prepare_decision
from scripts.retained_evidence_acceptance import run_until_intent

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = ROOT / 'autonomous-oss-remediation-workspaces/run-20261003T191151Z-240bca87/artifacts'


def historical_events():
    events = []
    for line in (HISTORICAL / 'events.jsonl').read_text().splitlines():
        event = json.loads(line)
        if event.get('artifact') and event.get('type') == 'adk_interaction':
            detail = json.loads((HISTORICAL / 'agent/interactions' / Path(event['artifact']).name).read_text())
            raw = json.dumps(detail, sort_keys=True, default=str).encode()
            if len(raw) != event['bytes'] or hashlib.sha256(raw).hexdigest() != event['sha256']:
                raise ValueError('Historical interaction binding mismatch')
            event.update(detail)
        events.append(event)
    return events


def response_script(events):
    """Replay observable call batches; empty completions stand in for unrecorded text.

    Historical traces do not retain every provider response. Empty outputs are
    explicit diagnostic controls, not a claim to reconstruct hidden responses.
    """
    steps = []
    for turn in range(1, 7):
        calls = [e for e in events if e.get('turn') == turn and e.get('interactionType') == 'tool_call']
        groups = {}
        for call in calls:
            groups.setdefault(call['eventId'], []).append({'functionCall': {'name': call['name'], 'args': call['arguments']}})
        steps.extend(groups.values())
        if turn < 6:
            steps.append([])
    return steps


async def inspect_variant(vertex=False):
    events = historical_events()
    steps = response_script(events)
    initial = next(e['message'] for e in events if e.get('interactionType') == 'turn_started')
    wire = []
    declaration = None
    with tempfile.TemporaryDirectory() as temporary:
        fixture = prepare_decision(RunWorkspace.create(temporary), 'evidence-conflict')
        session = default_agent_session_factory(fixture.capabilities, 'gemini-2.5-flash')
        # Explicit inert clients: transport is intercepted after actual SDK request conversion.
        client = (genai.Client(vertexai=True, project='offline-project', location='us-central1', credentials=AnonymousCredentials())
                  if vertex else genai.Client(vertexai=False, api_key='offline-placeholder'))
        session.agent.model.__dict__['api_client'] = client

        async def intercept(method, path, request_dict, http_options=None):
            nonlocal declaration
            functions = [f for tool in request_dict.get('tools', []) for f in tool.get('functionDeclarations', [])]
            intent = next(f for f in functions if f['name'] == 'submit_cycle_intent')
            if declaration is None:
                declaration = intent
            elif declaration != intent:
                raise AssertionError('Intent declaration changed during unknown-call recovery')
            parts = [p for content in request_dict.get('contents', []) for p in content.get('parts', [])]
            feedback = [p['functionResponse'] for p in parts if 'functionResponse' in p]
            continuations = [p['text'] for p in parts if p.get('text', '').startswith('Cycle 1 Problem Analysis')]
            wire.append({'request': len(wire) + 1, 'callableNames': [f['name'] for f in functions],
                         'intentDeclarationSha256': hashlib.sha256(json.dumps(intent, sort_keys=True).encode()).hexdigest(),
                         'systemInstructionSha256': hashlib.sha256(json.dumps(request_dict.get('systemInstruction'), sort_keys=True).encode()).hexdigest(),
                         'initialInputPresent': any(p.get('text') == initial for p in parts),
                         'correctionResponses': feedback, 'continuationMessages': continuations})
            if not steps:
                raise AssertionError('Unexpected extra provider request')
            response = {'candidates': [{'content': {'role': 'model', 'parts': steps.pop(0)}, 'finishReason': 'STOP'}]}
            return types.HttpResponse(headers={}, body=json.dumps(response))

        error = None
        try:
            with patch.object(client._api_client, 'async_request', side_effect=intercept):
                await run_until_intent(session, fixture.lifecycle, initial)
        except IntentToolRecoveryExhausted as exc:
            error = str(exc)
        finally:
            await session.close()
            await client.aio.aclose()
            client.close()
        trace = [json.loads(line) for line in fixture.trace.events_path.read_text().splitlines()]
        response_attempts = sorted({p['response']['attempt'] for request in wire for p in request['correctionResponses']})
        names = set(wire[0]['callableNames'])
        schema_text = json.dumps(declaration)
        checks = {
            'onlyRegisteredTools': names == fixture.capabilities.available_tool_names(),
            'inventedNamesAbsentFromDeclaration': all(name not in schema_text for name in ('SubmitCycleIntentAnswers', 'SubmitCycleIntentAnswersEvidence', 'google:python_interpreter')),
            'initialInputReachesEveryRequest': all(r['initialInputPresent'] for r in wire),
            'nineCorrectionsReachLaterRequests': response_attempts == list(range(1, 10)),
            'continuationCountsReachProvider': all(any(f'{count} unregistered tool call(s)' in m for r in wire for m in r['continuationMessages']) for count in (3, 6)),
            'sharedTenAttemptsTwoBlocked': fixture.lifecycle.cycles[1].intent_attempts == 10 and sum(e['type'] == 'checkpoint_attempt_blocked' for e in trace) == 2,
            'noAcceptedIntent': fixture.lifecycle.cycles[1].intent is None,
            'expectedExhaustion': error is not None and not steps,
        }
        return {'variant': 'vertex' if vertex else 'gemini-api', 'classification': 'offline_transport_reconstruction',
                'versions': {p: importlib.metadata.version(p) for p in ('google-adk', 'google-genai', 'pydantic')},
                'historicalInitialInputSha256': hashlib.sha256(initial.encode()).hexdigest(),
                'providerIntentDeclaration': declaration, 'requests': wire, 'checks': checks,
                'passed': all(checks.values()), 'terminalError': error,
                'limits': 'Existing fixture limits unchanged; no paid calls; no supplied valid Intent.'}


def compact_evidence(result):
    """Retain repeated feedback once, with per-request references proving delivery."""
    feedback, continuations, requests = {}, {}, []
    for request in result['requests']:
        item = {k: v for k, v in request.items() if k not in {'correctionResponses', 'continuationMessages'}}
        item['correctionAttempts'] = []
        for response in request['correctionResponses']:
            key = str(response['response']['attempt'])
            if key in feedback and feedback[key] != response:
                raise ValueError('Conflicting response for the same checkpoint attempt')
            feedback[key] = response
            item['correctionAttempts'].append(key)
        item['continuationSha256'] = []
        for message in request['continuationMessages']:
            key = hashlib.sha256(message.encode()).hexdigest()
            continuations[key] = message
            item['continuationSha256'].append(key)
        requests.append(item)
    return {**result, 'requests': requests, 'feedbackByAttempt': feedback,
            'continuationBySha256': continuations}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for vertex in (False, True):
        result = asyncio.run(inspect_variant(vertex))
        with (args.output_dir / (result['variant'] + '.json')).open('x', encoding='utf-8') as output:
            json.dump(compact_evidence(result), output, indent=2)
            output.write('\n')
        results.append({k: result[k] for k in ('variant', 'passed', 'checks')})
    print(json.dumps(results, indent=2))
    raise SystemExit(0 if all(r['passed'] for r in results) else 1)
