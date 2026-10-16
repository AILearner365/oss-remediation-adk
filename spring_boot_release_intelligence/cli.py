from __future__ import annotations

import argparse
from pathlib import Path

from .experiment import Experiment
from .a5_experiment import A5Experiment, qualify_a5_storage, rerun_a5_quiet
from .a6_experiment import (A6Experiment, capture_a6_network_telemetry,
                            finalize_a6_evidence, qualify_a6_storage)
from .charts import generate_a5_charts, generate_a6_charts


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    live = sub.add_parser("run-live")
    live.add_argument("--output", type=Path, required=True)
    a5 = sub.add_parser("run-a5")
    a5.add_argument("--output", type=Path, required=True)
    a5.add_argument("--cache-root", type=Path, required=True)
    a5.add_argument("--reference", type=Path, required=True)
    qualify = sub.add_parser("qualify-a5-storage")
    qualify.add_argument("--results", type=Path, required=True)
    qualify.add_argument("--output", type=Path, required=True)
    qualify.add_argument("--cache-root", type=Path, required=True)
    charts = sub.add_parser("generate-a5-charts")
    charts.add_argument("--results", type=Path, required=True)
    charts.add_argument("--output", type=Path, required=True)
    rerun = sub.add_parser("rerun-a5-quiet")
    rerun.add_argument("--results", type=Path, required=True)
    rerun.add_argument("--output", type=Path, required=True)
    rerun.add_argument("--cache-root", type=Path, required=True)
    a6 = sub.add_parser("run-a6")
    a6.add_argument("--output", type=Path, required=True)
    a6.add_argument("--cache-root", type=Path, required=True)
    a6.add_argument("--reference", type=Path, required=True)
    qualify6 = sub.add_parser("qualify-a6-storage")
    qualify6.add_argument("--results", type=Path, required=True)
    qualify6.add_argument("--output", type=Path, required=True)
    qualify6.add_argument("--cache-root", type=Path, required=True)
    telemetry6 = sub.add_parser("capture-a6-telemetry")
    telemetry6.add_argument("--results", type=Path, required=True)
    telemetry6.add_argument("--output", type=Path, required=True)
    telemetry6.add_argument("--cache-root", type=Path, required=True)
    charts6 = sub.add_parser("generate-a6-charts")
    charts6.add_argument("--results", type=Path, required=True)
    charts6.add_argument("--output", type=Path, required=True)
    finalize6 = sub.add_parser("finalize-a6-evidence")
    finalize6.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "run-live":
        result = Experiment(args.output).run()
        print(args.output / "results-v2.json")
        print(f"cells={len(result['cells'])} elapsed={result['measurements']['total_elapsed_seconds']:.3f}s")
    elif args.command == "run-a5":
        result = A5Experiment(args.output, args.cache_root, args.reference).run()
        print(args.output / "results-a5.json")
        print(f"accuracy={result['accuracy']['passed_count']}/{result['accuracy']['total_count']} "
              f"elapsed={result['measurements']['total_elapsed_seconds']:.3f}s")
    elif args.command == "qualify-a5-storage":
        result = qualify_a5_storage(args.results, args.output, args.cache_root)
        print(args.output / "bootstrap-control.json")
        print(f"qualified={result['qualified_no_application_dependency_jars']} "
              f"overlaps={len(result['reclassified_overlap_paths'])}")
    elif args.command == "generate-a5-charts":
        for path in generate_a5_charts(args.results, args.output):
            print(path)
    elif args.command == "rerun-a5-quiet":
        result = rerun_a5_quiet(args.results, args.output, args.cache_root)
        print(f"accuracy={result['accuracy']['passed_count']}/{result['accuracy']['total_count']} "
              f"fresh={result['a5']['fresh']['elapsed_seconds']:.3f}s "
              f"warm={result['a5']['warm']['elapsed_seconds']:.3f}s")
    elif args.command == "run-a6":
        result = A6Experiment(args.output, args.cache_root, args.reference).run()
        accuracy = result["a6_selection_accuracy_against_a5"]
        print(args.output / "results-a6.json")
        print(f"accuracy={accuracy['passed_count']}/{accuracy['total_count']} "
              f"elapsed={result['measurements']['total_elapsed_seconds']:.3f}s")
    elif args.command == "qualify-a6-storage":
        result = qualify_a6_storage(args.results, args.output, args.cache_root)
        print(args.output / "bootstrap-control.json")
        print(f"qualified={result['qualified_no_application_dependency_jars']} "
              f"overlaps={len(result['reclassified_overlap_paths'])}")
    elif args.command == "capture-a6-telemetry":
        result = capture_a6_network_telemetry(
            args.results, args.output, args.cache_root)
        print(f"fresh_events={result['fresh_transfers']['successful_transfer_events']} "
              f"warm_events={result['warm_transfers']['successful_transfer_events']}")
    elif args.command == "generate-a6-charts":
        for path in generate_a6_charts(args.results, args.output):
            print(path)
    elif args.command == "finalize-a6-evidence":
        result = finalize_a6_evidence(args.results)
        print(f"override_candidates={len(result['application_override_evidence']['candidates'])}")


if __name__ == "__main__":
    main()
