from .execution import BudgetExceeded, ExecutionBudget, ProcessRunner
from .research import HttpResearchProvider, ResearchProvider, ResearchResult, ResearchStatus
from .workspace_io import WorkspaceIO

__all__ = [
    "BudgetExceeded",
    "DeveloperCapabilitySet",
    "ExecutionBudget",
    "HttpResearchProvider",
    "ProcessRunner",
    "ResearchProvider",
    "ResearchResult",
    "ResearchStatus",
    "WorkspaceIO",
]


def __getattr__(name: str):
    """Keep optional ADK-backed toolsets out of deterministic imports."""
    if name == "DeveloperCapabilitySet":
        from .toolset import DeveloperCapabilitySet
        return DeveloperCapabilitySet
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
