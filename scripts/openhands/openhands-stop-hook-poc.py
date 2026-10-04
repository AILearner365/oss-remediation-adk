#!/usr/bin/env python3
"""Minimal OpenHands SDK 1.50.0 Stop Hook proof of concept.

Purpose:
- prove that a native Stop hook can deny the first completion attempt;
- inject deterministic failure feedback into the same conversation;
- let the same agent continue;
- allow a later completion attempt.

This deliberately does NOT call the Gate 2 remediation validator.
"""

from __future__ import annotations

import argparse
import os
import stat
import tempfile
from pathlib import Path

from openhands.sdk import Conversation, LLM
from openhands.sdk.event import HookExecutionEvent
from openhands.sdk.hooks import HookConfig, HookDefinition, HookMatcher
try:
    from openhands.tools.preset.default import get_default_agent
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Missing openhands-tools. Run this POC with both matching 1.50.0 packages: "
        'uv run --with "openhands-sdk[vertex]==1.50.0" '
        '--with "openhands-tools==1.50.0" '
        "python scripts/openhands/openhands-stop-hook-poc.py"
    ) from exc


DENY_MARKER = "TEST_VALIDATION_FAILED"
SUCCESS_MARKER = "STOP_HOOK_POC_OK"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prove OpenHands native Stop-hook deny -> feedback -> resume -> allow."
    )
    parser.add_argument(
        "--model",
        default=os.environ.get(
            "OPENHANDS_POC_MODEL", "vertex_ai/gemini-2.5-flash"
        ),
        help="OpenHands/LiteLLM model name.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=12,
        help="Hard bound for agent iterations in this POC.",
    )
    return parser.parse_args()


def write_dummy_hook(workspace: Path) -> Path:
    hook_path = workspace / "dummy_stop_hook.sh"
    hook_path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

COUNT_FILE=".stop-hook-count"
count=0
if [ -f "$COUNT_FILE" ]; then
  count="$(cat "$COUNT_FILE")"
fi
count=$((count + 1))
printf '%s\n' "$count" > "$COUNT_FILE"

if [ "$count" -eq 1 ]; then
  printf '%s\n' '{"decision":"deny","reason":"dummy validator intentionally rejects the first completion attempt","additionalContext":"TEST_VALIDATION_FAILED: deterministic dummy validator rejected the first finish attempt. Continue in this same conversation and attempt to finish again."}'
  exit 2
fi

printf '%s\n' '{"decision":"allow","reason":"dummy validator allows the second or later completion attempt"}'
exit 0
"""
    )
    hook_path.chmod(
        hook_path.stat().st_mode
        | stat.S_IXUSR
        | stat.S_IXGRP
        | stat.S_IXOTH
    )
    return hook_path


def event_contains_marker(event: object, marker: str) -> bool:
    try:
        if hasattr(event, "model_dump_json"):
            return marker in event.model_dump_json()
    except Exception:
        pass
    return marker in repr(event)


def main() -> int:
    args = parse_args()

    if args.max_iterations < 2:
        raise SystemExit("--max-iterations must be at least 2")

    if args.model.startswith("vertex_ai/"):
        missing = [
            name
            for name in ("VERTEXAI_PROJECT", "VERTEXAI_LOCATION")
            if not os.environ.get(name)
        ]
        if missing:
            raise SystemExit(
                "Missing required Vertex environment variable(s): "
                + ", ".join(missing)
            )

    with tempfile.TemporaryDirectory(prefix="openhands-stop-hook-poc-") as tmp:
        workspace = Path(tmp)
        hook_path = write_dummy_hook(workspace)

        hook_config = HookConfig(
            stop=[
                HookMatcher(
                    matcher="*",
                    hooks=[
                        HookDefinition(
                            command=str(hook_path),
                            timeout=15,
                        )
                    ],
                )
            ]
        )

        llm = LLM(
            usage_id="openhands-stop-hook-poc",
            model=args.model,
            api_key=None,
        )
        agent = get_default_agent(llm=llm, cli_mode=True)
        conversation = Conversation(
            agent=agent,
            workspace=str(workspace),
            hook_config=hook_config,
            max_iteration_per_run=args.max_iterations,
            stuck_detection=True,
        )

        try:
            conversation.send_message(
                "Create a file named proof.txt containing exactly "
                f"{SUCCESS_MARKER}. Then finish. "
                "If a stop hook rejects completion, use its feedback and attempt "
                "to finish again. Do not delete .stop-hook-count."
            )
            conversation.run()

            status = conversation.state.execution_status
            status_value = getattr(status, "value", str(status))

            stop_events = [
                event
                for event in conversation.state.events
                if isinstance(event, HookExecutionEvent)
                and event.hook_event_type == "Stop"
            ]
            feedback_seen = any(
                event_contains_marker(event, DENY_MARKER)
                for event in conversation.state.events
            )

            proof_file = workspace / "proof.txt"
            proof_ok = (
                proof_file.exists()
                and proof_file.read_text().strip() == SUCCESS_MARKER
            )

            count_file = workspace / ".stop-hook-count"
            stop_count = (
                int(count_file.read_text().strip())
                if count_file.exists()
                else 0
            )

            first_denied = bool(stop_events) and bool(stop_events[0].blocked)
            later_allowed = any(not event.blocked for event in stop_events[1:])
            finished = status_value == "finished"

            print(f"MODEL={args.model}")
            print(f"CONVERSATION_ID={conversation.state.id}")
            print(f"FINAL_STATUS={status_value}")
            print(f"STOP_HOOK_INVOCATIONS={stop_count}")
            print(f"STOP_HOOK_EVENTS={len(stop_events)}")
            print(f"FIRST_STOP_DENIED={first_denied}")
            print(f"LATER_STOP_ALLOWED={later_allowed}")
            print(f"DENIAL_FEEDBACK_OBSERVED={feedback_seen}")
            print(f"PROOF_FILE_OK={proof_ok}")

            passed = all(
                [
                    finished,
                    stop_count >= 2,
                    len(stop_events) >= 2,
                    first_denied,
                    later_allowed,
                    feedback_seen,
                    proof_ok,
                ]
            )

            print(f"POC_RESULT={'PASS' if passed else 'FAIL'}")
            return 0 if passed else 1
        finally:
            conversation.close()


if __name__ == "__main__":
    raise SystemExit(main())
