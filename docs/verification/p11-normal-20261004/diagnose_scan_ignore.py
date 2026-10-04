"""Offline diagnostic only; no runtime policy changes or vulnerability verdict."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from autonomous_oss_remediation_agent.evidence import scanner_copy_ignore

root = Path(__file__).resolve().parents[3]
workspace = root / 'autonomous-oss-remediation-workspaces/run-20261004T031259Z-4d965e41'
scanner = '/home/kavya_parivarababu/bin/osv-scanner'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True, help='New evidence file; must not already exist')
args = parser.parse_args()
if args.output.exists():
    parser.error('Output already exists; preserve retained evidence')
output = []
with tempfile.TemporaryDirectory(prefix='scan-ignore-diagnostic-', dir=workspace / 'temp') as temp:
    staged = Path(temp) / 'repository'
    shutil.copytree(workspace / 'repository', staged, ignore=scanner_copy_ignore)
    assert (staged / 'pom.xml').is_file()
    for variant, extra in [('default-ignore', []), ('no-ignore', ['--no-ignore'])]:
        command = [scanner, 'scan', 'source', '-r', str(staged), '--format', 'json', '--data-source=native', '--offline', '--no-resolve', *extra]
        result = subprocess.run(command, cwd=staged, capture_output=True, text=True, timeout=60)
        output.append(dict(variant=variant, command=command, exitCode=result.returncode, stdout=result.stdout, stderr=result.stderr))
with args.output.open('x') as stream:
    stream.write(json.dumps({'controlledOfflineDiagnostic': True, 'stagedPomPresent': True, 'results': output}, indent=2)+'\n')
for result in output:
    print(result['variant'], result['exitCode'], result['stderr'][-2500:])
