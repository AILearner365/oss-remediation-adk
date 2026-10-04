#!/usr/bin/env python3
"""Read SDK event JSON files; write an observable-only, sanitized evidence export.

No SDK imports, network calls, runtime locks, or source writes. Output must be new.
This is a review aid, not a general guarantee that arbitrary logs contain no secrets.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re


def scrub(value):
    if isinstance(value, dict):
        return {k: ('[REDACTED]' if re.search(r'(?i)(api.?key|password|secret|access.?token|authorization)', k)
                    else scrub(v)) for k, v in value.items()
                if k not in {'reasoning_content', 'thinking_blocks', 'thought', 'signature'}}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r'__thought__\S+', '[OPAQUE_SIGNATURE_OMITTED]', value)
        value = re.sub(r'(?im)^.*Your Cloud Platform project in this session is set to .*$', '[Cloud project banner redacted]', value)
        value = re.sub(r'(?i)(Bearer\s+)[\w.\-/+=]+', r'\1[REDACTED]', value)
        value = re.sub(r'(?i)((?:api[_-]?key|session[_-]?key|access[_-]?token|password)\s*[=:]\s*)[^\s,;]+', r'\1[REDACTED]', value)
        return value
    return value


def project(event):
    out = {k: event[k] for k in ('id', 'timestamp', 'source', 'parent_id', 'kind') if k in event}
    kind = event['kind']
    if kind == 'ActionEvent':
        out.update({k: event[k] for k in ('action', 'summary', 'tool_name', 'tool_call_id', 'security_risk') if k in event})
    elif kind == 'ObservationEvent':
        out.update({k: event[k] for k in ('tool_name', 'tool_call_id') if k in event})
        out['observation'] = {k: v for k, v in event['observation'].items() if k != 'metadata'}
    elif kind == 'MessageEvent':
        out['message'] = {k: event['llm_message'][k] for k in ('role', 'content') if k in event['llm_message']}
    elif kind == 'SystemPromptEvent':
        out['system_prompt'] = event['system_prompt']
        out['tool_names'] = [t.get('title') or t.get('name') or t.get('function', {}).get('name') for t in event.get('tools', [])]
    elif kind == 'ConversationStateUpdateEvent':
        out['key'] = event['key']
        if event['key'] in ('execution_status', 'last_user_message_id'):
            out['value'] = event['value']
        else:
            out['value_omitted'] = True
    else:
        raise ValueError(f'Unreviewed event kind: {kind}')
    return scrub(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('events', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    source, dest = args.events.resolve(), args.output.resolve()
    if dest == source or source in dest.parents:
        parser.error('Output must be outside the source event directory')
    files = sorted(source.glob('event-*.json'))
    if not files:
        parser.error('No SDK event JSON files found')
    rows, manifest = [], []
    for p in files:
        raw = p.read_bytes()
        row = project(json.loads(raw))
        row['sequence'] = int(p.name.split('-')[1])
        rows.append(row)
        manifest.append({'source_file': p.name, 'sha256': hashlib.sha256(raw).hexdigest()})
    dest.mkdir(parents=True, exist_ok=False)
    body = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows)
    (dest / 'events.jsonl').write_text(body)
    (dest / 'manifest.json').write_text(json.dumps({
        'source': str(source), 'event_count': len(rows),
        'export_sha256': hashlib.sha256(body.encode()).hexdigest(),
        'omissions': 'Reasoning/thought fields, opaque thought signatures, raw LLM responses, observation metadata, stats values, system dynamic context and tool schemas. Credential patterns and cloud project banner redacted. Review before publication.',
        'files': manifest}, indent=2) + '\n')
    print(f'Exported {len(rows)} events to {dest}')


if __name__ == '__main__':
    main()
