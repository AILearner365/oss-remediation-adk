"""SDK tool for agent-authored cycle records; no acceptance or delivery authority."""
from typing import Literal

from openhands.sdk.tool import Action, Observation, ToolDefinition, ToolExecutor, register_tool

from . import journal
from .contract import context
from .files import Blocked, lock


class CycleAction(Action):
    record_type: Literal["decision", "intent", "outcome"]
    document: dict


class CycleObservation(Observation):
    pass


class CycleExecutor(ToolExecutor):
    def __call__(self, action, conversation=None):
        from pathlib import Path
        state = Path(conversation.workspace.working_dir).parent
        try:
            _, bound, _ = context(state)
            if str(conversation.state.id) != bound["conversationId"]:
                raise Blocked("Native conversation does not own this cycle record")
            with lock(state):
                result = journal.record(state, action.record_type, action.document)
            return CycleObservation.from_text(f"Recorded cycle {result['cycle']} {action.record_type}, tree {result['tree']}")
        except Blocked as exc:
            return CycleObservation.from_text(str(exc), is_error=True)


class CycleEvidenceTool(ToolDefinition):
    @classmethod
    def create(cls, conv_state):
        return [cls(description="At a material strategy choice/change, optionally record decision: strategy, rationale; "
                    "observations/evidence_refs optional. At completion record outcome: summary, goal_status "
                    "(candidate_ready or bounded_failure); remaining_uncertainty/evidence_refs optional. "
                    "Not required per command/edit or to authorize acceptance. Legacy intent is supported for old records.",
                    action_type=CycleAction, observation_type=CycleObservation, executor=CycleExecutor())]


register_tool(CycleEvidenceTool.name, CycleEvidenceTool)
