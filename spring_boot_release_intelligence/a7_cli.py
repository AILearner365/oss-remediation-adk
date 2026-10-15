from __future__ import annotations

import argparse
import json
from pathlib import Path

from .a7 import (OsvBatchClient, inventory_from_a5, materialize_candidate,
                 minimal_cyclonedx, reconcile, validate_minimal_cyclonedx,
                 write_json)
from .maven import parse_tgf


def _inventory(tree: Path):
    return inventory_from_a5(parse_tgf(tree, []))


def main() -> None:
    parser = argparse.ArgumentParser(description="Bounded A7 experiment helpers")
    commands = parser.add_subparsers(dest="command", required=True)
    materialize = commands.add_parser("materialize")
    materialize.add_argument("source", type=Path)
    materialize.add_argument("destination", type=Path)
    materialize.add_argument("candidate")
    sbom = commands.add_parser("minimal-sbom")
    sbom.add_argument("tree", type=Path); sbom.add_argument("output", type=Path)
    sbom.add_argument("--seed", required=True)
    compare = commands.add_parser("reconcile")
    compare.add_argument("tree", type=Path); compare.add_argument("bom", type=Path)
    batch = commands.add_parser("osv-batch")
    batch.add_argument("trees", type=Path, nargs="+")
    batch.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "materialize":
        value = materialize_candidate(args.source, args.destination, args.candidate)
        print(json.dumps(value, sort_keys=True))
    elif args.command == "minimal-sbom":
        value = minimal_cyclonedx(_inventory(args.tree), serial_seed=args.seed)
        errors = validate_minimal_cyclonedx(value)
        if errors: raise SystemExit("; ".join(errors))
        write_json(args.output, value); print(args.output)
    elif args.command == "reconcile":
        value = json.loads(args.bom.read_text(encoding="utf-8"))
        print(json.dumps(reconcile(_inventory(args.tree), value), sort_keys=True))
    else:
        value = OsvBatchClient().query([_inventory(path) for path in args.trees])
        write_json(args.output, value); print(args.output)


if __name__ == "__main__":
    main()
