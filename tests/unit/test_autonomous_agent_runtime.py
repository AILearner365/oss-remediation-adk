from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from autonomous_oss_remediation_agent.agent import GoogleAdkAgentSession
from autonomous_oss_remediation_agent.capabilities.execution import BudgetExceeded, ExecutionBudget
from autonomous_oss_remediation_agent.config import ExecutionBudgetConfig


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
