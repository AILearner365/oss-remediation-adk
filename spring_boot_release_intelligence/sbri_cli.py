from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .report import write_report
from .release_selection import select_candidates
from .standalone import Evaluator, discover_boot_version


def _csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="sbri", description="Spring Boot Release Intelligence")
    sub = parser.add_subparsers(dest="command", required=True)
    evaluate = sub.add_parser("evaluate", help="compare Spring Boot releases")
    evaluate.add_argument("--project", type=Path, required=True)
    group = evaluate.add_mutually_exclusive_group()
    group.add_argument("--range", dest="release_range")
    group.add_argument("--releases")
    evaluate.add_argument("--max-candidates", type=int)
    evaluate.add_argument("--output", type=Path, default=Path("output"))
    evaluate.add_argument("--maven")
    evaluate.add_argument("--settings", type=Path)
    evaluate.add_argument("--profiles")
    evaluate.add_argument("--modules")
    evaluate.add_argument("--scopes")
    evaluate.add_argument("--scanner")
    evaluate.add_argument("--severities")
    evaluate.add_argument("--timeout", type=int)
    evaluate.add_argument("--scanner-report", action="append", default=[],
                          metavar="VERSION=PATH", help="pre-generated CycloneDX vulnerability report")
    evaluate.add_argument("--config", type=Path, help="JSON defaults; CLI values take precedence")
    args = parser.parse_args(argv)
    if args.command != "evaluate":
        return 2
    try:
        configured = json.loads(args.config.read_text()) if args.config else {}
        baseline = discover_boot_version(args.project)["version"]
        releases, selection = select_candidates(
            baseline, versions=args.releases, ranges=args.release_range,
            config=configured, max_candidates=args.max_candidates,
        )
        reports = {}
        for value in args.scanner_report:
            version, path = value.split("=", 1); reports[version] = Path(path)
        evaluator = Evaluator(args.project, releases, args.output,
            maven=args.maven or configured.get("maven", "mvn"),
            settings=args.settings or (Path(configured["settings"]) if configured.get("settings") else None),
            profiles=_csv(args.profiles) or configured.get("profiles", []),
            modules=_csv(args.modules) or configured.get("modules", []),
            scopes=_csv(args.scopes) or configured.get("scopes", ["compile", "runtime"]),
            scanner=args.scanner or configured.get("scanner", "osv-scanner"),
            severities=[value.upper() for value in (_csv(args.severities) or
                        configured.get("severities", ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]))],
            timeout=args.timeout or configured.get("timeout", 300), scanner_reports=reports)
        result = evaluator.evaluate()
        result["execution"]["release_selection"] = selection
        (args.output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        write_report(result, args.output / "report.html")
        print(args.output / "result.json"); print(args.output / "report.html")
        return {"SUCCESS": 0, "PARTIAL": 3, "FAILURE": 2}.get(result["status"], 2)
    except Exception as error:
        print(f"sbri: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
