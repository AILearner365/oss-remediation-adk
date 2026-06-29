from __future__ import annotations

from .workspace_manager import WorkspaceManager

# MVP alias. ArtifactStore may later add retention, indexing, and schema validation behavior.
ArtifactStore = WorkspaceManager
