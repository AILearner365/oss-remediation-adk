"""SDK-native evidence tools; fixed task authority, no acceptance/delivery action."""
from pathlib import Path

from openhands.sdk.tool import Action, Observation, ToolDefinition, ToolExecutor, register_tool

from .contract import context
from .files import Blocked
from . import capabilities


def task_state(conversation):
    state = Path(conversation.workspace.working_dir).parent
    _, bound, _ = context(state)
    if str(conversation.state.id) != bound["conversationId"]:
        raise Blocked("Native conversation does not own this evidence task")
    return state


class ValidateAction(Action):
    pass


class EvidenceObservation(Observation):
    pass


class ValidateExecutor(ToolExecutor):
    def __call__(self, action, conversation=None):
        import json
        try:
            result = capabilities.self_validate(task_state(conversation))
            return EvidenceObservation.from_text(json.dumps({k: v for k, v in result.items() if k != "evaluation"}))
        except Exception as exc:
            return EvidenceObservation.from_text(str(exc) if isinstance(exc, Blocked)
                else "Self-validation infrastructure failure: " + type(exc).__name__, is_error=True)


class ValidateRemediationTool(ToolDefinition):
    @classmethod
    def create(cls, conv_state):
        return [cls(description="Full-project self-validation using the same Maven/OSV/policy validator. "
            "Inspect retained findings and reassess. No arguments can change baseline, policy or destination. "
            "Never authorizes acceptance/delivery or consumes independent Stop attempts.",
            action_type=ValidateAction, observation_type=EvidenceObservation, executor=ValidateExecutor())]


class SbriAction(Action):
    versions: list[str] | None = None
    ranges: list[str] | None = None
    scopes: list[str] | None = None


class SbriExecutor(ToolExecutor):
    def __call__(self, action, conversation=None):
        import json
        try:
            result = capabilities.sbri(task_state(conversation), versions=action.versions,
                                       ranges=action.ranges, scopes=action.scopes)
            return EvidenceObservation.from_text(json.dumps(result))
        except Exception as exc:
            return EvidenceObservation.from_text(str(exc) if isinstance(exc, Blocked)
                else "SBRI infrastructure failure: " + type(exc).__name__, is_error=True)


class SbriIntelligenceTool(ToolDefinition):
    @classmethod
    def create(cls, conv_state):
        return [cls(description="Optional existing SBRI CLI intelligence on the current tree. "
            "Request explicit versions OR release ranges, optional scopes; omitted inputs use approved task defaults. "
            "Approved Maven profiles and tool settings are forwarded automatically; fresh cached results are reused, stale/known-inconclusive results retried within budget. "
            "Coverage/rank is bounded evidence, not compatibility or a prescribed Boot upgrade. "
            "Unavailable/partial results do not mean zero findings. Results retain raw evidence and reuse matching requests.",
            action_type=SbriAction, observation_type=EvidenceObservation, executor=SbriExecutor())]


register_tool(ValidateRemediationTool.name, ValidateRemediationTool)
register_tool(SbriIntelligenceTool.name, SbriIntelligenceTool)
