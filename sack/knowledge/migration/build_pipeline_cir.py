"""Build a canonical package from lossless Pipeline metadata version 2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from sack.knowledge.graph.builders.pipeline import build_pipeline_records_from_metadata
from sack.knowledge.graph.manifest import GraphPackageManifest
from sack.knowledge.graph.merge import merge_graph_records
from sack.knowledge.graph.package_writer import CanonicalPackageWriter
from sack.knowledge.graph.validation import validate_graph


class PipelinePackageBuildError(RuntimeError):
    """Raised when persisted Pipeline artifacts cannot form a valid package."""


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelinePackageBuildError(f"Cannot read JSON artifact {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise PipelinePackageBuildError(f"JSON artifact must contain an object: {path}")
    return value


def _load_complete_analyses(base_dir: Path) -> dict[str, Mapping[str, Any]]:
    analyses: dict[str, Mapping[str, Any]] = {}
    insights_dir = base_dir / "core_insights"
    if not insights_dir.is_dir():
        return analyses
    for path in sorted(insights_dir.glob("*_complete_analysis.json")):
        document = _load_json(path)
        pipeline_uri = document.get("pipeline_uri")
        if not isinstance(pipeline_uri, str) or not pipeline_uri:
            raise PipelinePackageBuildError(f"Complete analysis is missing pipeline_uri: {path}")
        previous = analyses.get(pipeline_uri)
        if previous is not None and previous != document:
            raise PipelinePackageBuildError(
                f"Conflicting complete analyses for Pipeline {pipeline_uri}"
            )
        analyses[pipeline_uri] = document
    return analyses


def build_pipeline_package(
    *,
    pipeline_graphs_dir: str | Path,
    output_dir: str | Path,
    build_id: str,
    generated_at: str | None = None,
) -> GraphPackageManifest:
    base_dir = Path(pipeline_graphs_dir)
    if not base_dir.is_dir():
        raise PipelinePackageBuildError(
            f"Pipeline graph directory does not exist: {base_dir}"
        )
    metadata_paths = sorted(base_dir.glob("*/*_metadata.json"))
    if not metadata_paths:
        raise PipelinePackageBuildError(f"No Pipeline metadata found under {base_dir}")
    analyses = _load_complete_analyses(base_dir)

    record_sets = []
    pipelines_with_insights = 0
    for path in metadata_paths:
        metadata = _load_json(path)
        pipeline_info = metadata.get("pipeline_info")
        if not isinstance(pipeline_info, Mapping):
            raise PipelinePackageBuildError(f"Metadata is missing pipeline_info: {path}")
        pipeline_uri = pipeline_info.get("uri")
        analysis = analyses.get(pipeline_uri)
        if analysis is not None:
            pipelines_with_insights += 1
        try:
            record_sets.append(
                build_pipeline_records_from_metadata(
                    metadata,
                    build_id=build_id,
                    complete_analysis=analysis,
                )
            )
        except ValueError as exc:
            raise PipelinePackageBuildError(f"Cannot convert {path}: {exc}") from exc

    merged = merge_graph_records(
        vertex_groups=(records.vertices for records in record_sets),
        edge_groups=(records.edges for records in record_sets),
    )
    validation = validate_graph(merged.vertices, merged.edges)
    if not validation.is_valid:
        details = "; ".join(
            f"{issue.code}:{issue.record_id or '-'}:{issue.message}"
            for issue in validation.errors[:20]
        )
        raise PipelinePackageBuildError(
            f"Canonical Pipeline graph validation failed with {len(validation.errors)} errors: "
            f"{details}"
        )

    writer = CanonicalPackageWriter(
        output_dir,
        build_id=build_id,
        generated_at=generated_at,
        metadata={
            "includes_pipeline_graph": True,
            "package_scope": "pipeline",
            "pipeline_count": len(record_sets),
            "pipelines_with_core_insights": pipelines_with_insights,
            "source_pipeline_graphs_dir": str(base_dir),
            "validation_error_count": 0,
            "validation_warning_count": len(validation.warnings),
        },
    )
    for vertex in merged.vertices:
        writer.write_vertex(vertex)
    for edge in merged.edges:
        writer.write_edge(edge)
    return writer.finalize()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export lossless Pipeline metadata as a canonical JSONL package."
    )
    parser.add_argument("--pipeline-graphs-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--build-id", required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    manifest = build_pipeline_package(
        pipeline_graphs_dir=args.pipeline_graphs_dir,
        output_dir=args.output_dir,
        build_id=args.build_id,
    )
    totals = manifest.to_dict()["totals"]
    print(
        "Canonical Pipeline package built: "
        f"vertices={totals['vertex_count']}, edges={totals['edge_count']}, "
        f"output={args.output_dir}"
    )


if __name__ == "__main__":
    main()
