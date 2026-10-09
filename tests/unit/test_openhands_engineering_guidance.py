from __future__ import annotations

import hashlib
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "openhands" / "openhands-gate2-stop-hook-run.py"
TASK_DOC = ROOT / "docs" / "experiments" / "openhands" / "GATE2-TASK.md"
TASK_DOC_SHA256 = "a22e74b44b2c251525a610a2343c4c6a146c80a57cefcc986b710e24c578ff6f"


try:
    import openhands.sdk  # noqa: F401
except ImportError:
    OPENHANDS_AVAILABLE = False
else:
    OPENHANDS_AVAILABLE = True


def load_runner():
    spec = importlib.util.spec_from_file_location("openhands_gate2_runner", RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load runner module from {RUNNER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(OPENHANDS_AVAILABLE, "openhands-sdk is not installed")
class OpenHandsEngineeringGuidanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load_runner()

    def make_llm(self):
        return self.runner.LLM(
            usage_id="openhands-guidance-offline-test",
            model="vertex_ai/gemini-2.5-flash",
            api_key=None,
        )

    def test_default_agent_is_unchanged(self) -> None:
        llm = self.make_llm()
        expected = self.runner.get_default_agent(llm=llm, cli_mode=True)
        actual = self.runner.build_agent(llm, engineering_guidance=False)
        self.assertEqual(actual.model_dump(), expected.model_dump())
        self.assertIsNone(actual.agent_context)

    def test_guidance_is_loaded_into_generated_system_context(self) -> None:
        llm = self.make_llm()
        default = self.runner.build_agent(llm, engineering_guidance=False)
        enabled = self.runner.build_agent(llm, engineering_guidance=True)
        guidance = self.runner.DEFAULT_ENGINEERING_GUIDANCE.read_text(
            encoding="utf-8"
        ).strip()
        guidance_lines = guidance.splitlines()

        self.assertEqual(len(guidance_lines), 5)
        self.assertTrue(all(line.startswith("- ") for line in guidance_lines))
        for prohibited in ("Maven", "Spring Boot", "dependency version", "command"):
            self.assertNotIn(prohibited, guidance)
        self.assertEqual(enabled.agent_context.system_message_suffix, guidance)
        self.assertIn(guidance, enabled.dynamic_context)
        self.assertEqual(
            enabled.model_dump(exclude={"agent_context"}),
            default.model_dump(exclude={"agent_context"}),
        )

    def test_configuration_switch_defaults_off_and_can_be_enabled(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch.object(
            sys, "argv", [str(RUNNER)]
        ):
            self.assertFalse(
                self.runner.parse_args().engineering_judgment_guidance
            )
        with patch.dict(
            os.environ,
            {self.runner.ENGINEERING_GUIDANCE_ENV: "1"},
            clear=True,
        ), patch.object(sys, "argv", [str(RUNNER)]):
            self.assertTrue(self.runner.parse_args().engineering_judgment_guidance)
        with patch.dict(
            os.environ,
            {self.runner.ENGINEERING_GUIDANCE_ENV: "1"},
            clear=True,
        ), patch.object(
            sys,
            "argv",
            [str(RUNNER), "--no-engineering-judgment-guidance"],
        ):
            self.assertFalse(
                self.runner.parse_args().engineering_judgment_guidance
            )

    def test_missing_or_unreadable_guidance_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.md"
            with self.assertRaisesRegex(
                SystemExit, "Unable to load engineering judgment guidance"
            ):
                self.runner.load_engineering_guidance(missing)
            with self.assertRaisesRegex(
                SystemExit, "Unable to load engineering judgment guidance"
            ):
                self.runner.load_engineering_guidance(Path(temp_dir))

    def test_task_contract_and_stop_hook_configuration_are_unchanged(self) -> None:
        self.assertEqual(
            hashlib.sha256(TASK_DOC.read_bytes()).hexdigest(),
            TASK_DOC_SHA256,
        )
        prompt = self.runner.extract_task_prompt(TASK_DOC)
        self.assertIn("Do not downgrade Spring Boot.", prompt)
        self.assertNotIn("engineering-judgment", prompt)

        target = Path("/tmp/target")
        baseline = Path("/tmp/state/baseline.json")
        validation = Path("/tmp/state/validation.json")
        hook_state = Path("/tmp/state/hook")
        config = self.runner.build_hook_config(
            target=target,
            baseline=baseline,
            validation=validation,
            hook_state=hook_state,
            max_denials=3,
        )
        self.assertEqual(len(config.stop), 1)
        self.assertEqual(config.stop[0].matcher, "*")
        self.assertEqual(len(config.stop[0].hooks), 1)
        hook = config.stop[0].hooks[0]
        self.assertEqual(hook.timeout, 1800)
        self.assertIn("GATE2_MAX_DENIALS=3", hook.command)
        self.assertIn(str(self.runner.DEFAULT_HOOK), hook.command)
        self.assertNotIn("engineering", hook.command.lower())


if __name__ == "__main__":
    unittest.main()
