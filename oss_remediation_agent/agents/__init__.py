from __future__ import annotations

import json
import os
from typing import Any, Protocol

from oss_remediation_agent.tools.workspace_artifact_tool import (
    list_workspace_artifacts,
    read_workspace_artifact,
    read_workspace_log_excerpt,
)


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

    When context enables workspace artifact access, this invoker supports a
    bounded tool-request loop. The model may first return a JSON object with a
    top-level ``toolRequests`` array. The invoker executes only registered
    WorkspaceArtifactTool functions against the current workspace, appends the
    tool results to context, and asks the model for the final JSON contract.
    """

    def __init__(self, model: str | None = None, max_tool_rounds: int | None = None):
        self.model = model or os.getenv("OSS_REMEDIATION_LLM_MODEL", "gemini-2.5-flash")
        self.max_tool_rounds = max_tool_rounds if max_tool_rounds is not None else int(os.getenv("OSS_REMEDIATION_MAX_TOOL_ROUNDS", "3"))

    def invoke(self, agent_name: str, context: dict[str, Any]) -> str:
        prompt = context.get("prompt")
        if not prompt:
            raise LLMInvocationError(f"{agent_name} context is missing prompt text.")

        try:
            from google import genai  # type: ignore
        except Exception as exc:  # pragma: no cover - environment dependent
            raise LLMInvocationError(
                "Google GenAI SDK is not available. Install ADK/GenAI runtime dependencies "
                "or inject a test LLMAgentInvoker."
            ) from exc

        client = genai.Client()
        payload = dict(context)
        payload.pop("prompt", None)
        payload.setdefault("toolResults", [])

        last_text = ""
        for round_index in range(self.max_tool_rounds + 1):
            contents = _build_contents(prompt, payload, round_index)
            try:
                response = client.models.generate_content(model=self.model, contents=contents)
                text = getattr(response, "text", None)
            except Exception as exc:  # pragma: no cover - environment dependent
                raise LLMInvocationError(f"{agent_name} LLM invocation failed: {exc}") from exc

            if not text:
                raise LLMInvocationError(f"{agent_name} LLM invocation returned empty output.")

            last_text = _strip_json_fence(text)
            parsed = _try_parse_json_object(last_text)
            tool_requests = parsed.get("toolRequests") if isinstance(parsed, dict) else None
            if not tool_requests:
                return last_text

            if round_index >= self.max_tool_rounds:
                raise LLMInvocationError(f"{agent_name} exceeded allowed workspace artifact tool rounds.")

            tool_results = _execute_workspace_artifact_tool_requests(payload, tool_requests)
            payload.setdefault("toolResults", []).append({
                "round": round_index + 1,
                "toolRequests": tool_requests,
                "toolResults": tool_results,
            })

        return last_text


class StaticJsonInvoker:
    """Test helper invoker that returns pre-supplied JSON outputs in order."""

    def __init__(self, outputs: list[str | dict[str, Any]]):
        self.outputs = list(outputs)

    def invoke(self, agent_name: str, context: dict[str, Any]) -> str | dict[str, Any]:
        if not self.outputs:
            raise LLMInvocationError(f"No static LLM output configured for {agent_name}.")
        return self.outputs.pop(0)


def _build_contents(prompt: str, payload: dict[str, Any], round_index: int) -> str:
    tool_instruction = ""
    if payload.get("toolAccess", {}).get("enabled"):
        tool_instruction = (
            "\n\nWorkspaceArtifactTool access is enabled. If the provided compact context is insufficient, "
            "return JSON with a top-level toolRequests array instead of the final contract. "
            "After tool results are supplied, return the final required JSON contract.\n"
            "Tool request shape:\n"
            "{\"toolRequests\":[{\"tool\":\"list_workspace_artifacts\",\"arguments\":{\"attempt_number\":1}},"
            "{\"tool\":\"read_workspace_artifact\",\"arguments\":{\"artifact_path\":\"attempt-1/validation-result.json\",\"mode\":\"compact\"}},"
            "{\"tool\":\"read_workspace_log_excerpt\",\"arguments\":{\"log_path\":\"attempt-1/build.log\",\"max_lines\":80}}]}\n"
            "Do not request files outside workspaceRoot. Do not use toolRequests in the final answer."
        )
    phase = "Use the following persisted workspace context. Return JSON only."
    if round_index > 0:
        phase = "Use the following persisted workspace context and toolResults. Return the final required JSON contract only."
    return f"{prompt}{tool_instruction}\n\n{phase}\n\n{json.dumps(payload, indent=2, sort_keys=True)}"


def _execute_workspace_artifact_tool_requests(payload: dict[str, Any], tool_requests: Any) -> list[dict[str, Any]]:
    workspace_root = payload.get("workspaceRoot")
    if not workspace_root:
        return [{"status": "FAILED", "failureCode": "WORKSPACE_ROOT_MISSING"}]
    if not isinstance(tool_requests, list):
        return [{"status": "FAILED", "failureCode": "INVALID_TOOL_REQUESTS", "message": "toolRequests must be a list."}]

    results: list[dict[str, Any]] = []
    for index, request in enumerate(tool_requests):
        if not isinstance(request, dict):
            results.append({"status": "FAILED", "failureCode": "INVALID_TOOL_REQUEST", "index": index})
            continue
        tool_name = request.get("tool") or request.get("name") or request.get("toolName")
        arguments = request.get("arguments") or request.get("args") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        try:
            if tool_name == "list_workspace_artifacts":
                result = list_workspace_artifacts(
                    str(workspace_root),
                    attempt_number=int(arguments.get("attempt_number") or arguments.get("attemptNumber") or payload.get("attemptNumber") or 1),
                )
            elif tool_name == "read_workspace_artifact":
                artifact_path = arguments.get("artifact_path") or arguments.get("artifactPath") or arguments.get("path")
                if not artifact_path:
                    raise ValueError("artifact_path is required")
                result = read_workspace_artifact(
                    str(workspace_root),
                    str(artifact_path),
                    mode=str(arguments.get("mode") or "compact"),
                    attempt_number=int(arguments.get("attempt_number") or arguments.get("attemptNumber") or payload.get("attemptNumber") or 1),
                )
            elif tool_name == "read_workspace_log_excerpt":
                log_path = arguments.get("log_path") or arguments.get("logPath") or arguments.get("path")
                if not log_path:
                    raise ValueError("log_path is required")
                result = read_workspace_log_excerpt(
                    str(workspace_root),
                    str(log_path),
                    keywords=arguments.get("keywords"),
                    max_lines=int(arguments.get("max_lines") or arguments.get("maxLines") or 80),
                )
            else:
                result = {"status": "FAILED", "failureCode": "UNSUPPORTED_TOOL", "tool": tool_name}
        except Exception as exc:
            result = {"status": "FAILED", "failureCode": "TOOL_EXECUTION_FAILED", "tool": tool_name, "error": str(exc)}
        results.append({"requestIndex": index, "tool": tool_name, "result": result})
    return results


def _try_parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```json"):
        stripped = stripped[len("```json"):].strip()
    elif stripped.startswith("```"):
        stripped = stripped[len("```"):].strip()
    if stripped.endswith("```"):
        stripped = stripped[:-3].strip()
    return stripped
