from __future__ import annotations

import asyncio
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from autonomous_oss_remediation_agent.agent import GoogleAdkAgentSession
from autonomous_oss_remediation_agent.capabilities.execution import BudgetExceeded, ExecutionBudget
from autonomous_oss_remediation_agent.config import ExecutionBudgetConfig
from autonomous_oss_remediation_agent.workspace import RunWorkspace, TraceStore


class _RecordingRunner:
    def __init__(self, events=None, delay_seconds: float = 0):
        self.session_service = SimpleNamespace(
            create_session=AsyncMock(return_value=SimpleNamespace(id="session-1"))
        )
        self.close = AsyncMock()
        self.events = list(events or ())
        self.delay_seconds = delay_seconds
        self.run_calls = []

    def run_async(self, **kwargs):
        self.run_calls.append(kwargs)

        async def events():
            if self.delay_seconds:
                await asyncio.sleep(self.delay_seconds)
            for event in self.events:
                yield event

        return events()


class GoogleAdkAgentSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_close_awaits_runner_cleanup(self):
        runner = _RecordingRunner()
        with patch("autonomous_oss_remediation_agent.agent.InMemoryRunner", return_value=runner):
            session = GoogleAdkAgentSession(MagicMock(), self._budget())

        await session.close()

        runner.close.assert_awaited_once_with()

    async def test_run_turn_passes_bounded_adk_run_config(self):
        runner = _RecordingRunner()
        budget = self._budget(max_llm_calls_per_turn=7)
        with patch("autonomous_oss_remediation_agent.agent.InMemoryRunner", return_value=runner):
            session = GoogleAdkAgentSession(MagicMock(), budget)

        await session.run_turn("inspect the repository")

        self.assertEqual(1, len(runner.run_calls))
        self.assertEqual(7, runner.run_calls[0]["run_config"].max_llm_calls)

    async def test_run_turn_enforces_wall_clock_timeout(self):
        runner = _RecordingRunner(delay_seconds=0.2)
        budget = self._budget(model_turn_timeout_seconds=0.01)
        with patch("autonomous_oss_remediation_agent.agent.InMemoryRunner", return_value=runner):
            session = GoogleAdkAgentSession(MagicMock(), budget)

        with self.assertRaisesRegex(BudgetExceeded, "Agent model turn exceeded"):
            await session.run_turn("inspect the repository")

    async def test_adk_interactions_preserve_order_calls_responses_and_error(self):
        call = SimpleNamespace(text="considering", function_call=None, function_response=None)
        function = SimpleNamespace(text=None, function_call=SimpleNamespace(name="missing_tool", args={"x": 1}), function_response=None)
        response = SimpleNamespace(text=None, function_call=None, function_response=SimpleNamespace(name="missing_tool", response={"error": "unavailable"}))
        runner = _RecordingRunner(events=[
            SimpleNamespace(id="e1", content=SimpleNamespace(role="model", parts=[call, function])),
            SimpleNamespace(id="e2", content=SimpleNamespace(role="tool", parts=[response])),
        ])
        with tempfile.TemporaryDirectory() as directory:
            trace = TraceStore(RunWorkspace.create(directory))
            with patch("autonomous_oss_remediation_agent.agent.InMemoryRunner", return_value=runner):
                session = GoogleAdkAgentSession(MagicMock(), self._budget(), trace=trace, cycle_provider=lambda: 2)
            result = await session.run_turn("continue")
            import json
            records = [json.loads(line) for line in trace.events_path.read_text().splitlines()]
            interactions = [r for r in records if r["type"] == "adk_interaction"]
            self.assertEqual(sorted(r["sequence"] for r in interactions), [r["sequence"] for r in interactions])
            self.assertEqual(["turn_started", "model_continuation", "tool_call", "tool_response", "turn_completed"],
                             [r["interactionType"] for r in interactions])
            self.assertEqual("missing_tool", interactions[2]["name"])
            self.assertEqual({"x": 1}, interactions[2]["arguments"])
            self.assertEqual({"error": "unavailable"}, interactions[3]["response"])
            self.assertEqual(2, interactions[2]["cycle"])
            self.assertEqual("considering", result.text)

    async def test_large_response_is_referenced_once(self):
        response = SimpleNamespace(text=None, function_call=None, function_response=SimpleNamespace(name="scan", response={"data": "x" * 20000}))
        runner = _RecordingRunner(events=[SimpleNamespace(id="e", content=SimpleNamespace(role="tool", parts=[response]))])
        with tempfile.TemporaryDirectory() as directory:
            trace = TraceStore(RunWorkspace.create(directory))
            with patch("autonomous_oss_remediation_agent.agent.InMemoryRunner", return_value=runner):
                session = GoogleAdkAgentSession(MagicMock(), self._budget(), trace=trace)
            await session.run_turn("continue")
            import json
            records = [json.loads(line) for line in trace.events_path.read_text().splitlines()]
            item = next(r for r in records if r.get("interactionType") == "tool_response")
            self.assertIn("artifact", item)
            self.assertNotIn("response", item)
            self.assertTrue(Path(item["artifact"]).is_file())

    @staticmethod
    def _budget(**overrides) -> ExecutionBudget:
        values = {
            "max_cycles": 2,
            "max_tool_calls": 8,
            "max_llm_calls_per_turn": 10,
            "command_timeout_seconds": 15,
            "model_turn_timeout_seconds": 30,
            "overall_timeout_seconds": 60,
            "max_returned_output_chars": 2000,
        }
        values.update(overrides)
        return ExecutionBudget(ExecutionBudgetConfig(**values))


if __name__ == "__main__":
    unittest.main()
