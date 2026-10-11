from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "scripts/openhands/validate-remediation-live-test.py"


def load_module():
    spec = importlib.util.spec_from_file_location("validate_remediation_live_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_prompt_requires_path_command_and_both_retained_evidence_types() -> None:
    module = load_module()

    assert "validate-remediation" in module.PROMPT
    assert "terminal PATH" in module.PROMPT
    assert "raw OSV report" in module.PROMPT
    assert "Maven coverage evidence" in module.PROMPT
    assert "Do not modify application code" in module.PROMPT


def test_event_sanitizer_removes_private_reasoning_and_credentials() -> None:
    module = load_module()

    sanitized = module.sanitize(
        {
            "reasoning_content": "private",
            "api_key": "not-for-evidence",
            "message": "Authorization: Bearer abc.def and password=hunter2",
        }
    )

    assert "reasoning_content" not in sanitized
    assert sanitized["api_key"] == "[REDACTED]"
    assert "abc.def" not in sanitized["message"]
    assert "hunter2" not in sanitized["message"]
