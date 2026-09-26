from __future__ import annotations

import asyncio
import hashlib
import json
import re
from contextlib import aclosing
from typing import Callable, Protocol

from google.adk.agents import LlmAgent, RunConfig
from google.adk.models import Gemini
from google.adk.runners import InMemoryRunner
from google.genai import types

from .capabilities.execution import BudgetExceeded, ExecutionBudget
from .capabilities.toolset import DeveloperCapabilitySet
from .models import AgentTurnResult
from .prompt import AGENT_INSTRUCTION
from .workspace import TraceStore


class IrrecoverableAgentSessionError(RuntimeError):
    """The ADK session cannot safely accept another turn."""


def create_remediation_agent(capabilities: DeveloperCapabilitySet, model: str) -> LlmAgent:
    return LlmAgent(
        name="autonomous_oss_remediation_agent",
        model=Gemini(
            model=model,
            retry_options=types.HttpRetryOptions(
                attempts=7,
                initial_delay=2.0,
                max_delay=30.0,
                exp_base=2.0,
                jitter=1.0,
            ),
        ),
        description="Autonomously investigates and remediates OSS vulnerabilities in one prepared repository.",
        instruction=AGENT_INSTRUCTION,
        tools=capabilities.adk_tools(),
        mode="chat",
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
        trace: TraceStore | None = None,
        cycle_provider: Callable[[], int] | None = None,
    ):
        self.agent = agent
        self.budget = budget
        self.app_name = app_name
        self.user_id = "remediation-runner"
        self.runner = InMemoryRunner(agent=agent, app_name=app_name)
        self.session_id: str | None = None
        self.trace = trace
        self.cycle_provider = cycle_provider or (lambda: 0)
        self._turn_number = 0
        self._interaction_number = 0

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
            try:
                session = await self.runner.session_service.create_session(
                    app_name=self.app_name, user_id=self.user_id,
                )
            except Exception as exc:
                raise IrrecoverableAgentSessionError(f"ADK session creation failed: {exc}") from exc
            self.session_id = session.id
        self._turn_number += 1
        turn = self._turn_number
        self._audit("turn_started", {"message": message}, turn)
        content = types.Content(role="user", parts=[types.Part(text=message)])
        texts: list[str] = []
        try:
            async with aclosing(
                self.runner.run_async(
                    user_id=self.user_id,
                    session_id=self.session_id,
                    new_message=content,
                    run_config=RunConfig(max_llm_calls=self.budget.config.max_llm_calls_per_turn),
                )
            ) as events:
                async for event in events:
                    self._audit_event(event, turn)
                    if event.content and event.content.parts:
                        text = "".join(part.text or "" for part in event.content.parts)
                        if text:
                            texts.append(text)
        except Exception as exc:
            self._audit("turn_failed", {"error": str(exc), "errorType": type(exc).__name__}, turn)
            raise
        self._audit("turn_completed", {}, turn)
        return AgentTurnResult(text=texts[-1] if texts else "")

    def _audit_event(self, event: object, turn: int) -> None:
        content = getattr(event, "content", None)
        for part in getattr(content, "parts", ()) or ():
            call = getattr(part, "function_call", None)
            response = getattr(part, "function_response", None)
            if call is not None:
                self._audit("tool_call", {"eventId": getattr(event, "id", None), "name": call.name,
                                          "arguments": dict(call.args or {})}, turn)
            if response is not None:
                self._audit("tool_response", {"eventId": getattr(event, "id", None), "name": response.name,
                                              "response": response.response}, turn)
            if getattr(part, "text", None):
                self._audit("model_continuation", {"eventId": getattr(event, "id", None),
                                                    "role": getattr(content, "role", None), "text": part.text}, turn)

    def _audit(self, kind: str, detail: dict, turn: int) -> None:
        if self.trace is None:
            return
        self._interaction_number += 1
        detail = _redact_interaction(detail)
        encoded = json.dumps(detail, sort_keys=True, default=str).encode("utf-8")
        if len(encoded) > 16_384:
            reference = str(self.trace.write_json(
                f"agent/interactions/{self._interaction_number:06d}.json", detail,
            ))
            detail = {"artifact": reference, "bytes": len(encoded),
                      "sha256": hashlib.sha256(encoded).hexdigest()}
        self.trace.append_event("adk_interaction", sequence=self._interaction_number,
                                turn=turn, cycle=self.cycle_provider(), sessionId=self.session_id,
                                interactionType=kind, **detail)

    async def close(self) -> None:
        await self.runner.close()


def _redact_interaction(value: object, key: str = "") -> object:
    if any(secret in key.lower() for secret in ("token", "password", "secret", "authorization", "api_key")):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _redact_interaction(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_interaction(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"(https?://)[^\s/@]+@", r"\1[REDACTED]@", value)
    return value

def default_agent_session_factory(capabilities: DeveloperCapabilitySet, model: str) -> AgentSession:
    return GoogleAdkAgentSession(
        create_remediation_agent(capabilities, model), capabilities.budget,
        trace=capabilities.trace,
        cycle_provider=lambda: capabilities.journal.active_cycle if capabilities.journal else 0,
    )
