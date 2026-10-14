from __future__ import annotations

import argparse
from pathlib import Path

from .experiment import Experiment
from .a5_experiment import A5Experiment, qualify_a5_storage, rerun_a5_quiet
from .charts import generate_a5_charts


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


if __name__ == "__main__":
    main()
