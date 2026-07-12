from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from oss_remediation_agent.agents import LLMInvocationError
from oss_remediation_agent.agents.remediation_outcome_analysis_agent import (
    build_outcome_analysis_context,
    persist_outcome_analysis_agent_output,
)
from oss_remediation_agent