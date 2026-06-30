from __future__ import annotations

import json
import os
from typing import Any, Protocol


class LLMInvocationError(RuntimeError):
    """Raised when an LLM-backed AI agent cannot be invoked."""


class LLMAgentInvoker(Protocol):
    """Runtime adapter for invoking LLM-backed agents.

    The orchestrator owns lifecycle and routing. AI agents own reasoning. This
    adapter boundary lets runtime code invoke Planning and Outcome Analysis
    agents without turning either agent into deterministic Python logic.
    """

    def invoke(self, agent_name: str, context: dict[str, Any]) -> str | dict[str, Any]:
        """Return the LLM agent's structured JSON output."""


class GoogleGenAIJsonInvoker:
    """Default JSON-only LLM invoker for ADK/Gemini runtime environments.

    The Google GenAI import is intentionally lazy so compile checks and unit
    tests do not require the SDK or credentials unless the runtime actually
    invokes an LLM-backed agent.
    """

    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("OSS_REMEDIATION_LLM_MODEL", "gemini-2.5-flash")

    def invoke(self, agent_name: str, context: dict[str, Any]) -> str:
        prompt = context.get("prompt")
        if not prompt:
            raise LLMInvocationError(f"{agent_name} context is missing prompt text.")

        payload = dict(context)
        payload.pop("prompt", None)
        contents = (
            f"{prompt}\n\n"
            "Use the following persisted workspace context. Return JSON only.\n\n"
            f"{json.dumps(payload, indent=2, sort_keys=True)}"
        )

        try:
            from google import genai  # type: ignore
        except Exception as exc:  # pragma: no cover - environment dependent
            raise LLMInvocationError(
                "Google GenAI SDK is not available. Install ADK/GenAI runtime dependencies "
                "or inject a test LLMAgentInvoker."
            ) from exc

        try:
            client = genai.Client()
            response = client.models.generate_content(model=self.model, contents=contents)
            text = getattr(response, "text", None)
        except Exception as exc:  # pragma: no cover - environment dependent
            raise LLMInvocationError(f"{agent_name} LLM invocation failed: {exc}") from exc

        if not text:
            raise LLMInvocationError(f"{agent_name} LLM invocation returned empty output.")
        return _strip_json_fence(text)


class StaticJsonInvoker:
    """Test helper invoker that returns pre-supplied JSON outputs in order."""

    def __init__(self, outputs: list[str | dict[str, Any]]):
        self.outputs = list(outputs)

    def invoke(self, agent_name: str, context: dict[str, Any]) -> str | dict[str, Any]:
        if not self.outputs:
            raise LLMInvocationError(f"No static LLM output configured for {agent_name}.")
        return self.outputs.pop(0)


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```json"):
        stripped = stripped[len("```json"):].strip()
    elif stripped.startswith("```"):
        stripped = stripped[len("```"):].strip()
    if stripped.endswith("```"):
        stripped = stripped[:-3].strip()
    return stripped
