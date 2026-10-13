from __future__ import annotations

import argparse
from pathlib import Path

from .experiment import Experiment


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    live = sub.add_parser("run-live")
    live.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "run-live":
        result = Experiment(args.output).run()
        print(args.output / "results.json")
        print(f"cells={len(result['cells'])} elapsed={result['measurements']['total_elapsed_seconds']:.3f}s")


if __name__ == "__main__":
    main()
