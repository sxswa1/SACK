from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASE_ROOT = PROJECT_ROOT / "data" / "eda_competitions"
DEFAULT_PROFILE_ROOT = PROJECT_ROOT / "storage" / "profiles" / "kaggle_profiles"
DEFAULT_PIPELINE_GRAPH_ROOT = PROJECT_ROOT / "storage" / "pipeline_graphs" / "kaggle_pipeline_graphs"
DEFAULT_SCHEMA_GRAPH = PROJECT_ROOT / "storage" / "timing" / "sack_kb_build_time" / "global_schema" / "kaggle_data_global_schema_graph.ttl"
DEFAULT_GRAPHDB_IMPORT_ROOT = Path.home() / "graphdb-import"


@dataclass
class TimedRun:
    name: str
    status: str
    seconds: float
    command: list[str]
    returncode: int | None
    stdout_tail: str = ""
    stderr_tail: str = ""
    note: str = ""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Profile SACK knowledge-base build cost with minimal reruns.",
    )
    parser.add_argument("--case", default="playground-series-s3e11", help="Representative case for single-case timing.")
    parser.add_argument("--pipeline-case", default="foursquare-location-matching", help="Representative case for pipeline abstraction timing.")
    parser.add_argument("--target-case-count", type=int, default=69, help="Case count used for paper-level extrapolation.")
    parser.add_argument("--output-dir", default="storage/timing/sack_kb_build_time")
    parser.add_argument("--run-single-profile", action="store_true", help="Actually rerun profile_data on one case.")
    parser.add_argument("--run-single-pipeline-abstraction", action="store_true", help="Actually rerun pipeline abstraction on one case.")
    parser.add_argument("--run-global-schema", action="store_true", help="Actually rerun data global schema build.")
    parser.add_argument("--run-graphdb-schema-import", action="store_true", help="Import the measured full schema TTL into a timing GraphDB repo.")
    parser.add_argument("--run-graphdb-pipeline-upload", action="store_true", help="Upload existing full pipeline TTL artifacts into a timing GraphDB repo.")
    parser.add_argument("--run-postgres-embeddings", action="store_true", help="Create and populate timing PostgreSQL/pgvector embedding DBs.")
    parser.add_argument(
        "--include-schema-similarity",
        action="store_true",
        help="Include O(n^2) column similarity in schema timing. Default skips it for low-cost probing.",
    )
    parser.add_argument(
        "--schema-max-columns",
        type=int,
        default=0,
        help="Optional smoke-test cap passed as SACK_SCHEMA_MAX_COLUMNS. 0 means no cap.",
    )
    parser.add_argument("--profile-timeout", type=int, default=3600)
    parser.add_argument("--pipeline-timeout", type=int, default=7200)
    parser.add_argument("--schema-timeout", type=int, default=7200)
    parser.add_argument("--graphdb-timeout", type=int, default=7200)
    parser.add_argument("--postgres-timeout", type=int, default=7200)
    args = parser.parse_args()

    output_dir = PROJECT_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    inventory = collect_inventory()
    timed_runs: list[TimedRun] = []

    if args.run_single_profile:
        timed_runs.append(
            run_single_case_profile(
                case_name=args.case,
                output_dir=output_dir,
                timeout_seconds=args.profile_timeout,
            )
        )
    else:
        timed_runs.append(
            TimedRun(
                name="single_case_profile",
                status="skipped",
                seconds=0.0,
                command=[],
                returncode=None,
                note="Pass --run-single-profile to rerun profile_data on one representative case.",
            )
        )

    if args.run_single_pipeline_abstraction:
        timed_runs.append(
            run_single_case_pipeline_abstraction(
                case_name=args.pipeline_case,
                output_dir=output_dir,
                timeout_seconds=args.pipeline_timeout,
            )
        )
    else:
        timed_runs.append(
            TimedRun(
                name="single_case_pipeline_abstraction",
                status="skipped",
                seconds=0.0,
                command=[],
                returncode=None,
                note="Pass --run-single-pipeline-abstraction to rerun abstract_pipelines on one representative case.",
            )
        )

    if args.run_global_schema:
        timed_runs.append(
            run_global_schema_build(
                output_dir=output_dir,
                timeout_seconds=args.schema_timeout,
                include_similarity=args.include_schema_similarity,
                max_columns=args.schema_max_columns,
            )
        )
    else:
        timed_runs.append(
            TimedRun(
                name="global_schema_build",
                status="skipped",
                seconds=0.0,
                command=[],
                returncode=None,
                note="Pass --run-global-schema to rerun build_data_global_schema over existing profiles.",
            )
        )

    if args.run_graphdb_schema_import:
        timed_runs.append(
            run_graphdb_schema_import(
                output_dir=output_dir,
                timeout_seconds=args.graphdb_timeout,
            )
        )
    else:
        timed_runs.append(
            TimedRun(
                name="graphdb_schema_import",
                status="skipped",
                seconds=0.0,
                command=[],
                returncode=None,
                note="Pass --run-graphdb-schema-import with GraphDB running to time full schema import.",
            )
        )

    if args.run_graphdb_pipeline_upload:
        timed_runs.append(
            run_graphdb_pipeline_upload(
                timeout_seconds=args.graphdb_timeout,
            )
        )
    else:
        timed_runs.append(
            TimedRun(
                name="graphdb_pipeline_upload",
                status="skipped",
                seconds=0.0,
                command=[],
                returncode=None,
                note="Pass --run-graphdb-pipeline-upload with GraphDB running to time full pipeline TTL upload.",
            )
        )

    if args.run_postgres_embeddings:
        timed_runs.extend(run_postgres_embeddings(timeout_seconds=args.postgres_timeout))
    else:
        timed_runs.extend(
            [
                TimedRun(
                    name="postgres_embedding_db_create",
                    status="skipped",
                    seconds=0.0,
                    command=[],
                    returncode=None,
                    note="Pass --run-postgres-embeddings with PostgreSQL/pgvector running to time DB creation.",
                ),
                TimedRun(
                    name="postgres_embedding_populate",
                    status="skipped",
                    seconds=0.0,
                    command=[],
                    returncode=None,
                    note="Pass --run-postgres-embeddings with PostgreSQL/pgvector running to time embedding population.",
                ),
            ]
        )

    result = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(PROJECT_ROOT),
        "target_case_count": args.target_case_count,
        "representative_case": args.case,
        "representative_pipeline_case": args.pipeline_case,
        "inventory": inventory,
        "timed_runs": [asdict(run) for run in timed_runs],
        "derived_metrics": derive_metrics(timed_runs, inventory, args.target_case_count),
        "estimates": build_estimates(timed_runs, args.target_case_count),
        "limitations": build_limitations(inventory),
    }

    json_path = output_dir / "sack_kb_build_time_result.json"
    md_path = output_dir / "sack_kb_build_time_report.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")

    print(f"Wrote JSON result: {json_path}")
    print(f"Wrote Markdown report: {md_path}")


def collect_inventory() -> dict[str, Any]:
    cases = sorted([path for path in DEFAULT_CASE_ROOT.iterdir() if path.is_dir()]) if DEFAULT_CASE_ROOT.exists() else []
    case_rows = []
    for case_dir in cases:
        raw_csvs = list((case_dir / "rawdata").glob("*.csv"))
        root_csvs = list(case_dir.glob("*.csv"))
        csvs = raw_csvs or root_csvs
        pre_eda = case_dir / "pre_insight_extraction" / "eda_insight.json"
        deep_eda = case_dir / "deep_insight_extraction" / "eda_insight.json"
        graph_dir = DEFAULT_PIPELINE_GRAPH_ROOT / case_dir.name
        ttl_files = list(graph_dir.glob("*.ttl")) if graph_dir.exists() else []
        metadata_files = list(graph_dir.glob("*_metadata.json")) if graph_dir.exists() else []
        notebooks_dir = case_dir / "notebooks"
        notebook_pipeline_dirs = []
        if notebooks_dir.is_dir():
            for notebook_dir in notebooks_dir.iterdir():
                if notebook_dir.is_dir() and (notebook_dir / "pipeline_info.json").exists():
                    notebook_pipeline_dirs.append(notebook_dir)
        case_rows.append(
            {
                "case": case_dir.name,
                "csv_count": len(csvs),
                "csv_bytes": sum(path.stat().st_size for path in csvs if path.exists()),
                "has_pre_eda": pre_eda.exists() and pre_eda.stat().st_size > 0,
                "has_deep_eda": deep_eda.exists() and deep_eda.stat().st_size > 0,
                "has_notebooks_dir": notebooks_dir.is_dir(),
                "notebook_pipeline_count": len(notebook_pipeline_dirs),
                "pipeline_ttl_count": len(ttl_files),
                "pipeline_metadata_count": len(metadata_files),
                "pipeline_ttl_bytes": sum(path.stat().st_size for path in ttl_files),
            }
        )

    profile_paths = list(DEFAULT_PROFILE_ROOT.glob("**/*.json")) if DEFAULT_PROFILE_ROOT.exists() else []
    competition_profiles = list((DEFAULT_PROFILE_ROOT / "competition_profiles").glob("*.json")) if (DEFAULT_PROFILE_ROOT / "competition_profiles").exists() else []
    eda_profiles = list((DEFAULT_PROFILE_ROOT / "eda_insight_profiles").glob("*.json")) if (DEFAULT_PROFILE_ROOT / "eda_insight_profiles").exists() else []
    pipeline_ttls = list(DEFAULT_PIPELINE_GRAPH_ROOT.glob("**/*.ttl")) if DEFAULT_PIPELINE_GRAPH_ROOT.exists() else []
    pipeline_metadata = list(DEFAULT_PIPELINE_GRAPH_ROOT.glob("**/*_metadata.json")) if DEFAULT_PIPELINE_GRAPH_ROOT.exists() else []
    core_insights = list((DEFAULT_PIPELINE_GRAPH_ROOT / "core_insights").glob("*_complete_analysis.json")) if (DEFAULT_PIPELINE_GRAPH_ROOT / "core_insights").exists() else []

    return {
        "case_root": str(DEFAULT_CASE_ROOT),
        "profile_root": str(DEFAULT_PROFILE_ROOT),
        "pipeline_graph_root": str(DEFAULT_PIPELINE_GRAPH_ROOT),
        "case_count": len(case_rows),
        "cases_with_csv": sum(row["csv_count"] > 0 for row in case_rows),
        "cases_with_pre_and_deep_eda": sum(row["has_pre_eda"] and row["has_deep_eda"] for row in case_rows),
        "cases_with_notebooks_dir": sum(row["has_notebooks_dir"] for row in case_rows),
        "cases_with_notebook_pipelines": sum(row["notebook_pipeline_count"] > 0 for row in case_rows),
        "notebook_pipeline_count": sum(row["notebook_pipeline_count"] for row in case_rows),
        "cases_with_pipeline_ttl": sum(row["pipeline_ttl_count"] > 0 for row in case_rows),
        "total_case_csv_bytes": sum(row["csv_bytes"] for row in case_rows),
        "profile_json_count": len(profile_paths),
        "competition_profile_count": len(competition_profiles),
        "eda_profile_count": len(eda_profiles),
        "pipeline_ttl_count": len(pipeline_ttls),
        "pipeline_metadata_count": len(pipeline_metadata),
        "core_insight_json_count": len(core_insights),
        "pipeline_ttl_bytes": sum(path.stat().st_size for path in pipeline_ttls),
        "case_rows": case_rows,
    }


def run_single_case_profile(case_name: str, output_dir: Path, timeout_seconds: int) -> TimedRun:
    source_case = DEFAULT_CASE_ROOT / case_name
    if not source_case.exists():
        return TimedRun(
            name="single_case_profile",
            status="failed",
            seconds=0.0,
            command=[],
            returncode=None,
            note=f"Representative case not found: {source_case}",
        )

    work_dir = output_dir / "single_case_profile"
    input_root = work_dir / "historical_cases"
    profiles_out = work_dir / "profiles"
    schema_out = work_dir / "schema" / "unused_schema.ttl"
    pipeline_out = work_dir / "pipeline_graphs"
    shutil.rmtree(work_dir, ignore_errors=True)
    input_root.mkdir(parents=True, exist_ok=True)
    profiles_out.mkdir(parents=True, exist_ok=True)
    pipeline_out.mkdir(parents=True, exist_ok=True)
    schema_out.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(source_case, input_root / case_name, target_is_directory=True)

    code = "from sack.knowledge.kg_governor.data_profiling.profile_data import profile_data; profile_data()"
    command = [sys.executable, "-c", code]
    env = os.environ.copy()
    env.update(
        {
            "SACK_HISTORICAL_CASE_PATH": str(input_root),
            "SACK_SACK_KNOWLEDGE_PROFILES_OUT_PATH": str(profiles_out),
            "SACK_SACK_KNOWLEDGE_SCHEMA_GRAPH_OUT_PATH": str(schema_out),
            "SACK_SACK_KNOWLEDGE_PIPELINE_GRAPHS_PATH": str(pipeline_out),
            "PYSPARK_PYTHON": sys.executable,
            "PYSPARK_DRIVER_PYTHON": sys.executable,
            "PYTHONPATH": str(PROJECT_ROOT),
        }
    )
    return timed_subprocess("single_case_profile", command, env, timeout_seconds, cwd=PROJECT_ROOT)


def run_single_case_pipeline_abstraction(case_name: str, output_dir: Path, timeout_seconds: int) -> TimedRun:
    source_case = DEFAULT_CASE_ROOT / case_name
    if not source_case.exists():
        return TimedRun(
            name="single_case_pipeline_abstraction",
            status="failed",
            seconds=0.0,
            command=[],
            returncode=None,
            note=f"Representative pipeline case not found: {source_case}",
        )
    if not (source_case / "notebooks").is_dir():
        return TimedRun(
            name="single_case_pipeline_abstraction",
            status="failed",
            seconds=0.0,
            command=[],
            returncode=None,
            note=f"Representative pipeline case has no notebooks directory: {source_case}",
        )

    work_dir = output_dir / "single_case_pipeline_abstraction"
    input_root = work_dir / "historical_cases"
    pipeline_out = work_dir / "pipeline_graphs"
    shutil.rmtree(work_dir, ignore_errors=True)
    input_root.mkdir(parents=True, exist_ok=True)
    pipeline_out.mkdir(parents=True, exist_ok=True)
    os.symlink(source_case, input_root / case_name, target_is_directory=True)

    code = "from sack.knowledge.kg_governor.pipeline_abstraction.abstract_pipelines import abstract_pipelines; abstract_pipelines(force_rerun=False)"
    command = [sys.executable, "-c", code]
    env = os.environ.copy()
    env.update(
        {
            "SACK_HISTORICAL_CASE_PATH": str(input_root),
            "SACK_SACK_KNOWLEDGE_PIPELINE_GRAPHS_PATH": str(pipeline_out),
            "PYTHONPATH": str(PROJECT_ROOT),
        }
    )
    run = timed_subprocess("single_case_pipeline_abstraction", command, env, timeout_seconds, cwd=PROJECT_ROOT)
    ttl_count = len(list(pipeline_out.glob("**/*.ttl"))) if pipeline_out.exists() else 0
    metadata_count = len(list(pipeline_out.glob("**/*_metadata.json"))) if pipeline_out.exists() else 0
    core_count = len(list((pipeline_out / "core_insights").glob("*_complete_analysis.json"))) if (pipeline_out / "core_insights").exists() else 0
    run.note = f"{run.note} case={case_name} ttl_count={ttl_count} metadata_count={metadata_count} core_insight_count={core_count}".strip()
    return run


def run_global_schema_build(output_dir: Path, timeout_seconds: int, include_similarity: bool, max_columns: int) -> TimedRun:
    work_dir = output_dir / "global_schema"
    graph_out = work_dir / "kaggle_data_global_schema_graph.ttl"
    pipeline_out = work_dir / "pipeline_graphs"
    shutil.rmtree(work_dir, ignore_errors=True)
    graph_out.parent.mkdir(parents=True, exist_ok=True)
    pipeline_out.mkdir(parents=True, exist_ok=True)

    code = "from sack.knowledge.kg_governor.data_global_schema_builder.build_data_global_schema import build_data_global_schema; build_data_global_schema()"
    command = [sys.executable, "-c", code]
    env = os.environ.copy()
    env.update(
        {
            "SACK_SACK_KNOWLEDGE_PROFILES_OUT_PATH": str(DEFAULT_PROFILE_ROOT),
            "SACK_SACK_KNOWLEDGE_SCHEMA_GRAPH_OUT_PATH": str(graph_out),
            "SACK_SACK_KNOWLEDGE_PIPELINE_GRAPHS_PATH": str(pipeline_out),
            "PYSPARK_PYTHON": sys.executable,
            "PYSPARK_DRIVER_PYTHON": sys.executable,
            "PYTHONPATH": str(PROJECT_ROOT),
        }
    )
    if not include_similarity:
        env["SACK_SKIP_SCHEMA_SIMILARITY"] = "1"
    if max_columns > 0:
        env["SACK_SCHEMA_MAX_COLUMNS"] = str(max_columns)
    run = timed_subprocess("global_schema_build", command, env, timeout_seconds, cwd=PROJECT_ROOT)
    if graph_out.exists():
        run.note = f"{run.note} graph_bytes={graph_out.stat().st_size}".strip()
    if not include_similarity:
        run.note = f"{run.note} column similarity skipped".strip()
    if max_columns > 0:
        run.note = f"{run.note} max_columns={max_columns}".strip()
    return run


def run_graphdb_schema_import(output_dir: Path, timeout_seconds: int) -> TimedRun:
    schema_path = output_dir / "global_schema" / "kaggle_data_global_schema_graph.ttl"
    if not schema_path.exists():
        schema_path = DEFAULT_SCHEMA_GRAPH
    if not schema_path.exists():
        return TimedRun(
            name="graphdb_schema_import",
            status="failed",
            seconds=0.0,
            command=[],
            returncode=None,
            note=f"Schema TTL not found: {schema_path}",
        )

    code = (
        "from sack.knowledge.storage_utils.graphdb_utils import create_graphdb_repo, populate_data_global_schema_graph; "
        "endpoint='http://localhost:7200'; repo='kaggle_timing_schema'; "
        f"create_graphdb_repo(endpoint, repo); populate_data_global_schema_graph({str(schema_path)!r}, repo, endpoint, {str(DEFAULT_GRAPHDB_IMPORT_ROOT)!r})"
    )
    command = [sys.executable, "-c", code]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    run = timed_subprocess("graphdb_schema_import", command, env, timeout_seconds, cwd=PROJECT_ROOT)
    run.note = f"{run.note} repo=kaggle_timing_schema graph_bytes={schema_path.stat().st_size}".strip()
    if "GraphDB import request failed" in run.stdout_tail or "GraphDB import failed" in run.stdout_tail:
        run.status = "failed"
    return run


def run_graphdb_pipeline_upload(timeout_seconds: int) -> TimedRun:
    if not DEFAULT_PIPELINE_GRAPH_ROOT.exists():
        return TimedRun(
            name="graphdb_pipeline_upload",
            status="failed",
            seconds=0.0,
            command=[],
            returncode=None,
            note=f"Pipeline graph root not found: {DEFAULT_PIPELINE_GRAPH_ROOT}",
        )

    code = (
        "from sack.knowledge.storage_utils.graphdb_utils import create_graphdb_repo, populate_pipeline_graphs; "
        "endpoint='http://localhost:7200'; repo='kaggle_timing_pipeline'; "
        f"create_graphdb_repo(endpoint, repo); populate_pipeline_graphs({str(DEFAULT_PIPELINE_GRAPH_ROOT)!r}, endpoint, repo)"
    )
    command = [sys.executable, "-c", code]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    run = timed_subprocess("graphdb_pipeline_upload", command, env, timeout_seconds, cwd=PROJECT_ROOT)
    upload_error_count = run.stdout_tail.count("Error uploading file:")
    run.note = (
        f"{run.note} repo=kaggle_timing_pipeline "
        f"ttl_count={len(list(DEFAULT_PIPELINE_GRAPH_ROOT.glob('**/*.ttl')))} "
        f"upload_error_count_in_tail={upload_error_count}"
    ).strip()
    if upload_error_count:
        run.status = "partial_success"
    return run


def run_postgres_embeddings(timeout_seconds: int) -> list[TimedRun]:
    col_db = "kaggle_timing_column_embeddings"
    comp_db = "kaggle_timing_competition_embeddings"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)

    create_code = (
        "from sack.knowledge.storage_utils.embedding_store_utils import create_columns_embedding_db, create_competition_embedding_db; "
        f"create_columns_embedding_db({col_db!r}); create_competition_embedding_db({comp_db!r})"
    )
    create_run = timed_subprocess(
        "postgres_embedding_db_create",
        [sys.executable, "-c", create_code],
        env,
        timeout_seconds,
        cwd=PROJECT_ROOT,
    )
    create_run.note = f"{create_run.note} column_db={col_db} competition_db={comp_db}".strip()

    populate_code = (
        "from sack.knowledge.storage_utils.embedding_store_utils import populate_embeddings; "
        f"populate_embeddings({str(DEFAULT_PROFILE_ROOT)!r}, {col_db!r}, {comp_db!r})"
    )
    populate_run = timed_subprocess(
        "postgres_embedding_populate",
        [sys.executable, "-c", populate_code],
        env,
        timeout_seconds,
        cwd=PROJECT_ROOT,
    )
    populate_run.note = f"{populate_run.note} profile_json_count={len(list(DEFAULT_PROFILE_ROOT.glob('**/*.json')))}".strip()
    return [create_run, populate_run]


def timed_subprocess(name: str, command: list[str], env: dict[str, str], timeout_seconds: int, cwd: Path) -> TimedRun:
    start = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        seconds = time.perf_counter() - start
        status = "success" if completed.returncode == 0 else "failed"
        return TimedRun(
            name=name,
            status=status,
            seconds=seconds,
            command=command,
            returncode=completed.returncode,
            stdout_tail=tail(completed.stdout),
            stderr_tail=tail(completed.stderr),
        )
    except subprocess.TimeoutExpired as exc:
        return TimedRun(
            name=name,
            status="timeout",
            seconds=time.perf_counter() - start,
            command=command,
            returncode=None,
            stdout_tail=tail(exc.stdout or ""),
            stderr_tail=tail(exc.stderr or ""),
            note=f"timeout_seconds={timeout_seconds}",
        )


def build_estimates(timed_runs: list[TimedRun], target_case_count: int) -> dict[str, Any]:
    runs = {run.name: run for run in timed_runs}
    estimates: dict[str, Any] = {}
    profile = runs.get("single_case_profile")
    if profile and profile.status == "success":
        estimates["profile_data_seconds_per_case"] = profile.seconds
        estimates["profile_data_seconds_for_target_cases"] = profile.seconds * target_case_count
    pipeline = runs.get("single_case_pipeline_abstraction")
    if pipeline and pipeline.status == "success":
        processed = parse_pipeline_stdout(pipeline.stdout_tail).get("pipelines_to_process")
        if processed:
            estimates["pipeline_abstraction_seconds_per_pipeline"] = pipeline.seconds / processed
            estimates["pipeline_abstraction_seconds_for_existing_69_pipeline_artifacts"] = (
                pipeline.seconds / processed * 669
            )
        estimates["pipeline_abstraction_seconds_per_case"] = pipeline.seconds
        estimates["pipeline_abstraction_seconds_for_target_cases"] = pipeline.seconds * target_case_count
    schema = runs.get("global_schema_build")
    if schema and schema.status == "success":
        estimates["global_schema_seconds_measured"] = schema.seconds
    if "profile_data_seconds_for_target_cases" in estimates and "global_schema_seconds_measured" in estimates:
        estimates["profile_plus_schema_seconds_for_target_cases"] = (
            estimates["profile_data_seconds_for_target_cases"] + estimates["global_schema_seconds_measured"]
        )
    return estimates


def derive_metrics(timed_runs: list[TimedRun], inventory: dict[str, Any], target_case_count: int) -> dict[str, Any]:
    runs = {run.name: run for run in timed_runs}
    derived: dict[str, Any] = {}
    profile = runs.get("single_case_profile")
    if profile and profile.status == "success":
        parsed = parse_profile_stdout(profile.stdout_tail)
        derived["single_case_profile_substages"] = parsed
        if parsed.get("metadata_eda_seconds") is not None:
            derived["metadata_eda_seconds_for_target_cases"] = parsed["metadata_eda_seconds"] * target_case_count
        if parsed.get("column_profile_seconds") is not None:
            derived["column_profile_seconds_for_target_cases"] = parsed["column_profile_seconds"] * target_case_count
    pipeline = runs.get("single_case_pipeline_abstraction")
    if pipeline and pipeline.status == "success":
        derived["single_case_pipeline_abstraction_substages"] = parse_pipeline_stdout(pipeline.stdout_tail)

    ttl_cases = inventory.get("cases_with_pipeline_ttl", 0)
    ttl_count = inventory.get("pipeline_ttl_count", 0)
    if ttl_cases:
        derived["pipeline_ttl_per_case"] = ttl_count / ttl_cases
        derived["pipeline_ttl_mb_per_case"] = inventory.get("pipeline_ttl_bytes", 0) / ttl_cases / (1024 * 1024)
    return derived


def parse_profile_stdout(stdout: str) -> dict[str, Any]:
    import re
    from datetime import datetime

    def parse_ts(pattern: str) -> datetime | None:
        match = re.search(pattern, stdout)
        if not match:
            return None
        return datetime.fromisoformat(match.group(1))

    start = parse_ts(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+) : Initializing Spark")
    metadata_done = parse_ts(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+) : Competition and EDA profile processing completed")
    column_start = parse_ts(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+) : Profiling \d+ columns")
    column_done = parse_ts(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+) : \d+ columns profiled")
    column_count_match = re.search(r": Profiling (\d+) columns", stdout)
    result: dict[str, Any] = {
        "profiled_column_count": int(column_count_match.group(1)) if column_count_match else None,
        "metadata_eda_seconds": None,
        "column_profile_seconds": None,
    }
    if start and metadata_done:
        result["metadata_eda_seconds"] = (metadata_done - start).total_seconds()
    if column_start and column_done:
        result["column_profile_seconds"] = (column_done - column_start).total_seconds()
    return result


def parse_pipeline_stdout(stdout: str) -> dict[str, Any]:
    import re

    result: dict[str, Any] = {
        "pipelines_to_process": None,
        "processed_pipeline_count": None,
        "core_insight_success_count": None,
        "pipeline_metadata_for_summary": None,
    }
    match = re.search(r"发现 (\d+) 个pipeline需要处理", stdout)
    if match:
        result["pipelines_to_process"] = int(match.group(1))
    match = re.search(r"成功处理 (\d+) 个pipeline，其中核心见解成功提取的有(\d+)个", stdout)
    if match:
        result["processed_pipeline_count"] = int(match.group(1))
        result["core_insight_success_count"] = int(match.group(2))
    match = re.search(r"总共 (\d+) 个pipeline元数据用于生成汇总文件", stdout)
    if match:
        result["pipeline_metadata_for_summary"] = int(match.group(1))
    return result


def build_limitations(inventory: dict[str, Any]) -> list[str]:
    limitations = []
    if inventory["cases_with_notebooks_dir"] == 0:
        limitations.append(
            "No data/eda_competitions/*/notebooks directories were found, so pipeline abstraction from source notebooks cannot be rerun in this workspace."
        )
    if inventory["cases_with_notebooks_dir"] > 0:
        limitations.append(
            "Pipeline abstraction timing is measured on one source-notebook case and extrapolated; full rerun cost still depends on notebook length, AST size, LLM latency, and retry behavior."
        )
    return limitations


def render_markdown(result: dict[str, Any]) -> str:
    inv = result["inventory"]
    estimates = result["estimates"]
    runs = result["timed_runs"]
    lines = [
        "# SACK Knowledge Base Build Timing Report",
        "",
        f"- Created at: `{result['created_at']}`",
        f"- Target extrapolation case count: `{result['target_case_count']}`",
        f"- Representative case: `{result['representative_case']}`",
        f"- Representative pipeline case: `{result['representative_pipeline_case']}`",
        "",
        "## Artifact Inventory",
        "",
        "| Item | Count / Size |",
        "| --- | ---: |",
        f"| Historical case directories | {inv['case_count']} |",
        f"| Cases with CSV files | {inv['cases_with_csv']} |",
        f"| Cases with complete pre/deep EDAInsight | {inv['cases_with_pre_and_deep_eda']} |",
        f"| Cases with notebooks directory | {inv['cases_with_notebooks_dir']} |",
        f"| Cases with notebook pipeline metadata | {inv['cases_with_notebook_pipelines']} |",
        f"| Source notebook pipelines | {inv['notebook_pipeline_count']} |",
        f"| Cases with pipeline TTL artifacts | {inv['cases_with_pipeline_ttl']} |",
        f"| Column/profile JSON files | {inv['profile_json_count']} |",
        f"| Competition profile JSON files | {inv['competition_profile_count']} |",
        f"| EDAInsight profile JSON files | {inv['eda_profile_count']} |",
        f"| Pipeline TTL files | {inv['pipeline_ttl_count']} |",
        f"| Pipeline metadata files | {inv['pipeline_metadata_count']} |",
        f"| CoreInsight analysis JSON files | {inv['core_insight_json_count']} |",
        f"| Pipeline TTL total size | {format_seconds_or_bytes(inv['pipeline_ttl_bytes'], is_bytes=True)} |",
        "",
        "## Timed Runs",
        "",
        "| Stage | Status | Seconds | Note |",
        "| --- | --- | ---: | --- |",
    ]
    for run in runs:
        lines.append(f"| {run['name']} | {run['status']} | {run['seconds']:.3f} | {run.get('note', '')} |")
    lines.extend(
        [
            "",
            "## Derived Metrics",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
        ]
    )
    derived = result.get("derived_metrics", {})
    substages = derived.get("single_case_profile_substages", {})
    if substages:
        lines.append(f"| Single-case profiled columns | {substages.get('profiled_column_count')} |")
        if substages.get("metadata_eda_seconds") is not None:
            lines.append(f"| Single-case metadata + EDA profile | {format_seconds_or_bytes(substages['metadata_eda_seconds'])} |")
        if substages.get("column_profile_seconds") is not None:
            lines.append(f"| Single-case column profiling | {format_seconds_or_bytes(substages['column_profile_seconds'])} |")
    if "metadata_eda_seconds_for_target_cases" in derived:
        lines.append(
            f"| Metadata + EDA profile extrapolated to {result['target_case_count']} cases | "
            f"{format_seconds_or_bytes(derived['metadata_eda_seconds_for_target_cases'])} |"
        )
    if "column_profile_seconds_for_target_cases" in derived:
        lines.append(
            f"| Column profiling extrapolated to {result['target_case_count']} cases | "
            f"{format_seconds_or_bytes(derived['column_profile_seconds_for_target_cases'])} |"
        )
    pipeline_substages = derived.get("single_case_pipeline_abstraction_substages", {})
    if pipeline_substages:
        if pipeline_substages.get("pipelines_to_process") is not None:
            lines.append(f"| Single-case pipelines queued for abstraction | {pipeline_substages.get('pipelines_to_process')} |")
        if pipeline_substages.get("processed_pipeline_count") is not None:
            lines.append(f"| Single-case pipelines processed | {pipeline_substages.get('processed_pipeline_count')} |")
        if pipeline_substages.get("core_insight_success_count") is not None:
            lines.append(f"| Single-case core-insight successes | {pipeline_substages.get('core_insight_success_count')} |")
    if "pipeline_ttl_per_case" in derived:
        lines.append(f"| Existing pipeline TTLs per TTL-backed case | {derived['pipeline_ttl_per_case']:.2f} |")
    if "pipeline_ttl_mb_per_case" in derived:
        lines.append(f"| Existing pipeline TTL artifact size per TTL-backed case | {derived['pipeline_ttl_mb_per_case']:.2f} MB |")

    lines.extend(
        [
            "",
            "## Extrapolated Estimates",
            "",
            "| Estimate | Value |",
            "| --- | ---: |",
        ]
    )
    if estimates:
        for key, value in estimates.items():
            lines.append(f"| {key} | {format_seconds_or_bytes(value)} |")
    else:
        lines.append("| No extrapolated timing available | Run timed stages to populate estimates |")

    lines.extend(["", "## Limitations", ""])
    for item in result["limitations"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Case-Level Inventory")
    lines.append("")
    lines.append("| Case | CSVs | Notebooks | Source Pipelines | Pre EDA | Deep EDA | Pipeline TTLs | TTL Size |")
    lines.append("| --- | ---: | --- | ---: | --- | --- | ---: | ---: |")
    for row in inv["case_rows"]:
        lines.append(
            f"| {row['case']} | {row['csv_count']} | {row['has_notebooks_dir']} | {row['notebook_pipeline_count']} | "
            f"{row['has_pre_eda']} | {row['has_deep_eda']} | "
            f"{row['pipeline_ttl_count']} | {format_seconds_or_bytes(row['pipeline_ttl_bytes'], is_bytes=True)} |"
        )
    return "\n".join(lines) + "\n"


def format_seconds_or_bytes(value: float, is_bytes: bool = False) -> str:
    if is_bytes:
        units = ["B", "KB", "MB", "GB"]
        size = float(value)
        unit = units[0]
        for unit in units:
            if size < 1024 or unit == units[-1]:
                break
            size /= 1024
        return f"{size:.2f} {unit}"
    seconds = float(value)
    if seconds < 60:
        return f"{seconds:.2f} s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.2f} min"
    return f"{minutes / 60:.2f} h"


def tail(text: str, max_chars: int = 12000) -> str:
    if not text:
        return ""
    return text[-max_chars:]


if __name__ == "__main__":
    main()
