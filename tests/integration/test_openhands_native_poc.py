import importlib.util
import json
import os
import subprocess
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

    def test_litellm_constraint_is_scoped_to_1551(self):
        from unittest.mock import patch
        old = {name: getattr(poc, name) for name in
               ("SERVER", "ROOT", "KEY_FILE", "BIN", "PID_FILE", "IDENTITIES",
                "INGRESS", "BACKEND", "AUTOMATION_PORT", "FRONTEND_PORT",
                "REPORT", "LOG_FILE")}
        try:
            with tempfile.TemporaryDirectory() as d:
                with patch.dict("os.environ", {"OH_POC_TMP": d}, clear=True):
                    poc.configure_server_version("1.55.1")
                    env = poc.environment()
                    constraint = Path(env["UV_CONSTRAINT"])
                    self.assertTrue(constraint.is_file())
                    self.assertEqual(constraint.read_text().strip(),
                                     "litellm==" + poc.POC_LITELLM_PIN)
                    poc.configure_server_version("1.54.0")
                    self.assertNotIn("UV_CONSTRAINT", poc.environment())
        finally:
            for name, value in old.items():
                setattr(poc, name, value)

    def test_vertex_wrapper_targets_only_pinned_native_agent_server(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            uvx = root / "real-uvx"
            uvx.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n", encoding="utf-8")
            uvx.chmod(0o700)
            with patch.object(poc, "ROOT", root), patch.object(poc, "SERVER", "1.55.1"), \
                 patch.object(poc.shutil, "which", return_value=str(uvx)):
                env = {"PATH": os.environ.get("PATH", "")}
                poc.install_vertex_uvx_wrapper(env)
                wrapper = Path(env["PATH"].split(os.pathsep)[0]) / "uvx"
                self.assertTrue(wrapper.is_file())
                target = subprocess.check_output(
                    [str(wrapper), "--from", "openhands-agent-server==1.55.1",
                     "--with", "openhands-sdk==1.55.1", "agent-server"],
                    text=True
                ).splitlines()
                self.assertEqual(target[:2], ["--with", "openhands-sdk[vertex]==1.55.1"])
                self.assertIn("openhands-agent-server==1.55.1", target)
                other = subprocess.check_output(
                    [str(wrapper), "--from", "openhands-automation==1.19.3", "uvicorn"],
                    text=True
                ).splitlines()
                self.assertEqual(other, ["--from", "openhands-automation==1.19.3", "uvicorn"])

    def test_vertex_preflight_uses_same_extra(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            called = []
            with patch.object(poc, "ROOT", Path(td)), \
                 patch.object(poc, "SERVER", "1.55.1"), \
                 patch.object(poc, "command", side_effect=lambda args, **kwargs: called.append(args) or ""):
                poc.warm_native_packages({"PATH": os.environ.get("PATH", "")})
            self.assertEqual(len(called), 3)
            for args in called[:2]:
                self.assertIn("openhands-sdk[vertex]==1.55.1", args)
            self.assertIn("google-cloud-aiplatform", " ".join(called[1]))

    def test_version_configuration_is_isolated(self):
        from unittest.mock import patch
        fields = ("SERVER", "ROOT", "INGRESS", "BACKEND", "AUTOMATION_PORT",
                  "FRONTEND_PORT", "BIN", "PID_FILE", "KEY_FILE",
                  "IDENTITIES", "REPORT", "LOG_FILE")
        original = {key: getattr(poc, key) for key in fields}
        try:
            with patch.dict("os.environ", {}, clear=True):
                poc.configure_server_version("1.54.0")
                old_root = poc.ROOT
                old_report = poc.REPORT
                self.assertEqual(poc.INGRESS, 8090)
                poc.configure_server_version("1.55.1")
                self.assertEqual(poc.SERVER, "1.55.1")
                self.assertEqual(poc.INGRESS, 8091)
                self.assertEqual(poc.BACKEND, 18910)
                self.assertNotEqual(poc.ROOT, old_root)
                self.assertNotEqual(poc.REPORT, old_report)
                self.assertNotEqual(poc.KEY_FILE.parent, old_root)
                self.assertTrue(str(poc.REPORT).endswith("native-integration-smoke-1.55.1.json"))
                poc.configure_server_version("1.54.0")
                self.assertEqual(poc.ROOT, old_root)
                self.assertEqual(poc.REPORT, old_report)
                with self.assertRaises(ValueError):
                    poc.configure_server_version("1.53.0")
        finally:
            for key, value in original.items():
                setattr(poc, key, value)

if __name__=='__main__': unittest.main()
