from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import RemediationRequest
from .integrations import configured_delivery_adapter
from .orchestrator import AutonomousRemediationOrchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the autonomous OSS remediation POC")
    parser.add_argument("request", type=Path, help="Path to a remediation request JSON file")
    parser.add_argument("--output", type=Path, help="Optional path for the final result JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    request = RemediationRequest.from_json_file(args.request)
    result = AutonomousRemediationOrchestrator(
        request,
        delivery_adapter_factory=lambda workspace, process_runner, trace: configured_delivery_adapter(
            request,
            process_runner,
            trace,
        ),
    ).run()
    serialized = json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0 if result.outcome.value == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
