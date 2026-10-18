import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('poc',str(Path(__file__).resolve().parents[2] / 'scripts' / 'openhands_native_poc.py'))
poc=importlib.util.module_from_spec(spec)
spec.loader.exec_module(poc)

class DummyResponse:
    status=200
    def __enter__(self): return self
    def __exit__(self, *exc): pass
    def read(self, n=-1): return b'<!doctype html><html><body>Canvas</body></html>'
class Opener:
    def open(self, *args, **kwargs): return DummyResponse()

class POCChecks(unittest.TestCase):
    def test_complete_fake_native_api(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            poc.ROOT=root
            poc.KEY_FILE=root/'session-key.txt'
            poc.IDENTITIES=root/'identities.json'
            poc.INGRESS=18080
            poc.LOOPBACK=Opener()
            poc.KEY_FILE.write_text('nonsecret')
            status={}
            def fake_http(method,path,payload=None,timeout=15):
                if path=='/server_info':
                    return {'version':poc.SERVER, 'sdk_version':poc.SERVER, 'tools_version':poc.SERVER,'capabilities':['idempotent_conversation_create_v1']}
                if method=='POST' and path.startswith('/api/conversations?'):
                    kind=payload['tags']['scenario']
                    status[kind]={'id':payload['conversation_id'],'execution_status':'idle', 'hook_config':payload.get('hook_config')}
                    return status[kind]
                if '/events/search' in path:
                    items=[{'text':'NATIVE_POC_CONTEXT'}] if 'remediation' in status and status['remediation'].get('context_sent') else []
                    return {'items':items}
                if method=='POST' and path.endswith('/events'):
                    status['remediation']['context_sent']=True
                    return {'success':True}
                if method=='GET' and path.startswith('/api/conversations/'):
                    kind=next((k for k,v in status.items() if v['id'] in path),None)
                    if kind: return status[kind]
                    raise poc.Failure('HTTP 404')
                raise AssertionError((method,path,payload))
            poc.http=fake_http
            r=poc.main_probe()
            self.assertTrue(r['verdict'].startswith('NATIVE_API_SMOKE_PASSED'))
            self.assertEqual(r['checks']['nativeStopHookAttached'],'PASS')
            self.assertEqual(r['checks']['normalIdleNoModelCall'],'PASS')
            self.assertEqual(r['checks']['remediationIdleNoModelCall'],'PASS')
            self.assertNotIn('Native /run executing Stop Hook',r['checks'])
            self.assertIn('Native /run executing Stop Hook',r['notProven'])
            # Rerun reuses conversation and context rather than resends.
            r2=poc.main_probe()
            self.assertEqual(r2['checks']['remediationConversationReused'],'PASS')
            self.assertEqual(r2['checks']['normalConversationReused'],'PASS')

if __name__=='__main__': unittest.main()
