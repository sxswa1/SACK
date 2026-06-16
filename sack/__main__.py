import argparse
import sys

from sack.framework import run_sack_pipeline
from sack.paths import SACK_CONFIG_PATH, SACK_PACKAGE_DIR


def _run_competition(args: argparse.Namespace) -> None:
    run_sack_pipeline(
        competition=args.competition,
        eda_start_phase=args.eda_start_phase,
        dsp_start_phase=args.dsp_start_phase,
        skip_eda=args.skip_eda,
        force_eda=args.force_eda,
        config_path=str(SACK_CONFIG_PATH),
        working_dir=SACK_PACKAGE_DIR,
    )


def _build_knowledge(_: argparse.Namespace) -> None:
    from sack.knowledge.build_knowledge import main as build_knowledge

    build_knowledge()


def _generate_edainsights(args: argparse.Namespace) -> None:
    from sack.get_history_edainsight import main as generate_edainsights

    sys.argv = [
        sys.argv[0],
        "--start-phase",
        args.start_phase,
        "--pool-size",
        str(args.pool_size),
    ]
    generate_edainsights()


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0].startswith("--"):
        argv = ["run", *argv]

    parser = argparse.ArgumentParser(description="Run unified SACK workflows.")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run SACK for one competition.")
    run_parser.add_argument("--competition", default="playground-series-s5e10")
    run_parser.add_argument("--eda-start-phase", default="Data Preparation")
    run_parser.add_argument("--dsp-start-phase", default="Feature Engineering")
    run_parser.add_argument("--skip-eda", action="store_true")
    run_parser.add_argument("--force-eda", action="store_true")
    run_parser.set_defaults(func=_run_competition)

    build_parser = subparsers.add_parser("build-knowledge", help="Build and load the historical case knowledge base.")
    build_parser.set_defaults(func=_build_knowledge)

    eda_parser = subparsers.add_parser("generate-edainsights", help="Generate EDAInsight files for historical cases.")
    eda_parser.add_argument("--start-phase", default="Data Preparation")
    eda_parser.add_argument("--pool-size", type=int, default=4)
    eda_parser.set_defaults(func=_generate_edainsights)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
