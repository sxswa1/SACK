import pytest

from sack.knowledge.graph.model import EdgeRecord, VertexRecord
from sack.knowledge.graph.package_reader import read_canonical_package
from sack.knowledge.graph.package_writer import CanonicalPackageWriter
from sack.knowledge.migration.merge_cir_packages import (
    PackageMergeError,
    merge_canonical_packages,
)


BUILD_ID = "merge-packages"
GENERATED_AT = "2026-09-22T00:00:00+00:00"


def _write(path, vertices, edges=(), build_id=BUILD_ID):
    with CanonicalPackageWriter(
        path,
        build_id=build_id,
        generated_at=GENERATED_AT,
    ) as writer:
        for vertex in sorted(vertices, key=lambda item: (item.label, item.uid)):
            writer.write_vertex(vertex)
        for edge in sorted(edges, key=lambda item: (item.edge_type, item.edge_uid)):
            writer.write_edge(edge)


def _dataset(properties, build_id=BUILD_ID):
    return VertexRecord.from_uri(
        uri="http://sack.local/resource/dataset/shared",
        label="Dataset",
        properties=properties,
        build_id=build_id,
    )


def test_merge_packages_combines_sparse_and_rich_shared_vertex(tmp_path):
    rich = _dataset({"name": "shared", "problem_type": "classification"})
    sparse = _dataset({"rdf_types_json": '["http://sack.local/ontology/Dataset"]'})
    pipeline = VertexRecord.from_uri(
        uri="http://sack.local/resource/dataset/shared/pipeline/one",
        label="Pipeline",
        properties={"title": "one"},
        build_id=BUILD_ID,
    )
    relation = EdgeRecord.from_endpoints(
        edge_type="IS_PART_OF",
        src_uid=pipeline.uid,
        dst_uid=sparse.uid,
        properties={},
        build_id=BUILD_ID,
    )
    profile_dir = tmp_path / "profile"
    pipeline_dir = tmp_path / "pipeline"
    _write(profile_dir, (rich,))
    _write(pipeline_dir, (sparse, pipeline), (relation,))

    manifest = merge_canonical_packages(
        input_dirs=(profile_dir, pipeline_dir),
        output_dir=tmp_path / "full",
        generated_at=GENERATED_AT,
    )
    package = read_canonical_package(tmp_path / "full")

    merged_dataset = next(item for item in package.vertices if item.label == "Dataset")
    assert merged_dataset.properties == {
        "name": "shared",
        "problem_type": "classification",
        "rdf_types_json": '["http://sack.local/ontology/Dataset"]',
    }
    assert manifest.to_dict()["totals"] == {
        "byte_count": manifest.to_dict()["totals"]["byte_count"],
        "edge_count": 1,
        "vertex_count": 2,
    }


def test_merge_packages_rejects_different_build_ids(tmp_path):
    first = _dataset({"name": "shared"})
    second = _dataset({"name": "shared"}, build_id="other-build")
    _write(tmp_path / "first", (first,))
    _write(tmp_path / "second", (second,), build_id="other-build")

    with pytest.raises(PackageMergeError, match="share one build_id"):
        merge_canonical_packages(
            input_dirs=(tmp_path / "first", tmp_path / "second"),
            output_dir=tmp_path / "full",
        )


def test_merge_packages_rejects_conflicting_properties(tmp_path):
    _write(tmp_path / "first", (_dataset({"name": "one"}),))
    _write(tmp_path / "second", (_dataset({"name": "two"}),))

    with pytest.raises(PackageMergeError, match="Canonical package conflict"):
        merge_canonical_packages(
            input_dirs=(tmp_path / "first", tmp_path / "second"),
            output_dir=tmp_path / "full",
        )
