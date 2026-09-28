import json

import pytest

from sack.knowledge.graph.model import VertexRecord
from sack.knowledge.graph.package_writer import CanonicalPackageWriter
from sack.knowledge.migration.export_tugraph import (
    IncompleteCanonicalGraphError,
    export_canonical_package,
)
from sack.knowledge.migration.merge_cir_packages import merge_canonical_packages


def test_export_cli_boundary_reads_verified_canonical_package(tmp_path):
    build_id = "cli-export-test"
    canonical = tmp_path / "canonical"
    dataset = VertexRecord.from_uri(
        uri="http://sack.local/resource/dataset/cli",
        label="Dataset",
        properties={"name": "cli"},
        build_id=build_id,
    )
    with CanonicalPackageWriter(
        canonical,
        build_id=build_id,
        generated_at="2026-09-22T00:00:00+00:00",
    ) as writer:
        writer.write_vertex(dataset)

    output = tmp_path / "tugraph"
    with pytest.raises(IncompleteCanonicalGraphError, match="requires a full CIR"):
        export_canonical_package(canonical_package=canonical, output_dir=output)

    manifest = export_canonical_package(
        canonical_package=canonical,
        output_dir=output,
        allow_partial=True,
    )

    config = json.loads((output / "import.config.json").read_text(encoding="utf-8"))
    assert manifest.build_id == build_id
    assert manifest.vertex_count == 1
    assert any(item["label"] == "Dataset" for item in config["files"])


def test_production_export_accepts_all_three_cir_sources(tmp_path):
    build_id = "full-export-test"
    dataset = VertexRecord.from_uri(
        uri="http://sack.local/resource/dataset/full",
        label="Dataset",
        properties={"name": "full"},
        build_id=build_id,
    )
    inputs = []
    for scope in ("profile-structure", "column-similarity", "pipeline"):
        path = tmp_path / scope
        with CanonicalPackageWriter(
            path,
            build_id=build_id,
            metadata={"package_scope": scope},
        ) as writer:
            if scope == "profile-structure":
                writer.write_vertex(dataset)
        inputs.append(path)
    merged = tmp_path / "merged"
    merge_canonical_packages(input_dirs=inputs, output_dir=merged)

    manifest = export_canonical_package(
        canonical_package=merged,
        output_dir=tmp_path / "tugraph",
    )

    assert manifest.vertex_count == 1
