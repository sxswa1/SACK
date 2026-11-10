"""Operator-only historical import and interrupted-run recovery commands."""

import argparse
import json
from pathlib import Path

from .runtime import import_report, recover_run
from .store import ReportStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="Report archive root; defaults to SACK_REPORT_ROOT.")
    commands = parser.add_subparsers(dest="command", required=True)
    importer = commands.add_parser("import-report")
    importer.add_argument("--experiment", required=True)
    importer.add_argument("--report", type=Path, required=True)
    importer.add_argument("--evidence", type=Path, help="Hash-bound completion receipt; omit to import as unknown.")
    recovery = commands.add_parser("recover-run")
    recovery.add_argument("--experiment", required=True)
    recovery.add_argument("--run-id", required=True)
    recovery.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    store = ReportStore(args.root)
    if args.command == "import-report":
        result = import_report(store, args.experiment, args.report, args.evidence)
    else:
        result = recover_run(store, args.experiment, args.run_id, args.workspace)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
