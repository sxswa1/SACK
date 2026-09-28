import json

import pytest

from sack.knowledge.migration.build_pipeline_cir import (
    PipelinePackageBuildError,
    build_pipeline_package,
)
from sack.knowledge.tests.test_pipeline_cir_builder import fixture_input


def write_pipeline_artifacts(base_dir, *, metadata_version=2):
    pipeline_info, nodes, files, libraries, insights = fixture_input()
    dataset_dir = base_dir / "titanic"
    dataset_dir.mkdir(parents=True)
    metadata = {
        "metadata_version": metadata_version,
        "pipeline_id": "pipeline-1",
        "dataset_name": "titanic",
        "pipeline_info": pipeline_info,
        "libraries": libraries,
        "nodes_count": len(nodes),
        "file_elements_count": len(files),
    }
    if metadata_version == 2:
        metadata["nodes"] = nodes
        metadata["file_elements"] = files
    (dataset_dir / "pipeline-1_metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )

    insights_dir = base_dir / "core_insights"
    insights_dir.mkdir()
    complete = {
        "pipeline_id": "pipeline-1",
        "pipeline_uri": pipeline_info["uri"],
        "dataset_name": "titanic",
        "core_insights": insights,
    }
    (insights_dir / "pipeline-1_complete_analysis.json").write_text(
        json.dumps(complete), encoding="utf-8"
    )


def test_pipeline_artifacts_build_a_valid_package(tmp_path):
    source = tmp_path / "pipeline_graphs"
    write_pipeline_artifacts(source)
    output = tmp_path / "canonical"

    manifest = build_pipeline_package(
        pipeline_graphs_dir=source,
        output_dir=output,
        build_id="pipeline-package-test",
        generated_at="2026-09-22T00:00:00+00:00",
    ).to_dict()

    assert manifest["metadata"]["pipeline_count"] == 1
    assert manifest["metadata"]["pipelines_with_core_insights"] == 1
    assert manifest["totals"]["vertex_count"] > 0
    assert manifest["totals"]["edge_count"] > 0
    assert (output / "vertices" / "statement.jsonl").exists()
    assert (output / "edges" / "has_parameter.jsonl").exists()


def test_legacy_metadata_requires_pipeline_rebuild(tmp_path):
    source = tmp_path / "pipeline_graphs"
    write_pipeline_artifacts(source, metadata_version=1)

    with pytest.raises(PipelinePackageBuildError, match="predates lossless version 2"):
        build_pipeline_package(
            pipeline_graphs_dir=source,
            output_dir=tmp_path / "canonical",
            build_id="pipeline-package-test",
        )
