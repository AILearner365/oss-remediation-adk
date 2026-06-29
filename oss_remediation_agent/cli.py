from __future__ import annotations

import argparse

from oss_remediation_agent.workflow import WorkflowOrchestrator


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the OSS remediation MVP workflow skeleton.")
    parser.add_argument("run", nargs="?")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--workspace", default="remediation-workspace")
    args = parser.parse_args()

    result = WorkflowOrchestrator(args.workspace).checkout_and_baseline(args.repo, args.branch)
    print(result)


if __name__ == "__main__":
    main()
