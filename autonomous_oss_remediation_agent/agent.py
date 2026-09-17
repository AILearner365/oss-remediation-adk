from __future__ import annotations

import asyncio
from contextlib import aclosing
from typing import Protocol

from google.adk.agents import LlmAgent, RunConfig
from google.adk.runners import InMemoryRunner
from google.genai import types

from .capabilities.execution import BudgetExceeded, ExecutionBudget
from .capabilities.toolset import DeveloperCapabilitySet
from .models import AgentTurnResult
from .prompt import AGENT_INSTRUCTION


def create_remediation_agent(capabilities: DeveloperCapabilitySet, model: str) -> LlmAgent:
    return LlmAgent(
        name="autonomous_oss_remediation_agent",
        model=model,
        description="Autonomously investigates and remediates OSS vulnerabilities in one prepared repository.",
        instruction=AGENT_INSTRUCTION,
        tools=capabilities.adk_tools(),
        mode="task",
    )


class AgentSession(Protocol):
    async def run_turn(self, message: str) -> AgentTurnResult: ...

    async def close(self) -> None: ...


class GoogleAdkAgentSession:
    def __init__(
        self,
        agent: LlmAgent,
        budget: ExecutionBudget,
        app_name: str = "autonomous_oss_remediation",
    ):
        self.agent = agent
        self.budget = budget
        self.app_name = app_name
        self.user_id = "remediation-runner"
        self.runner = InMemoryRunner(agent=agent, app_name=app_name)
        self.session_id: str | None = None

    async def run_turn(self, message: str) -> AgentTurnResult:
        timeout_seconds = self.budget.model_turn_timeout()
        try:
            return await asyncio.wait_for(self._run_turn(message), timeout=timeout_seconds)
        except TimeoutError as exc:
            raise BudgetExceeded(
                f"Agent model turn exceeded its {timeout_seconds:g}s wall-clock limit"
            ) from exc

    async def _run_turn(self, message: str) -> AgentTurnResult:
        if self.session_id is None:
            session = await self.runner.session_service.create_session(
                app_name=self.app_name,
                user_id=self.user_id,
            )
            self.session_id = session.id
        content = types.Content(role="user", parts=[types.Part(text=message)])
        texts: list[str] = []
        async with aclosing(
            self.runner.run_async(
                user_id=self.user_id,
                session_id=self.session_id,
                new_message=content,
                run_config=RunConfig(max_llm_calls=self.budget.config.max_llm_calls_per_turn),
            )
        ) as events:
            async for event in events:
                if event.content and event.content.parts:
                    text = "".join(part.text or "" for part in event.content.parts)
                    if text:
                        texts.append(text)
        return AgentTurnResult(text=texts[-1] if texts else "")

    async def close(self) -> None:
        await self.runner.close()


def default_agent_session_factory(capabilities: DeveloperCapabilitySet, model: str) -> AgentSession:
    return GoogleAdkAgentSession(create_remediation_agent(capabilities, model), capabilities.budget)
