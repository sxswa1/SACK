import json

import pytest

from sack.knowledge.graph.model import EdgeRecord, VertexRecord
from sack.knowledge.graph.package_reader import PackageReadError, read_canonical_package
from sack.knowledge.graph.package_writer import CanonicalPackageWriter


BUILD_ID = "reader-test"


def _write_package(path):
    dataset = VertexRecord.from_uri(
        uri="http://sack.local/resource/dataset/one",
        label="Dataset",
        properties={"name": "one"},
        build_id=BUILD_ID,
    )
    table = VertexRecord.from_uri(
        uri="http://sack.local/resource/dataset/one/table/train",
        label="Table",
        properties={"name": "train"},
        build_id=BUILD_ID,
    )
    edge = EdgeRecord.from_endpoints(
        edge_type="IS_PART_OF",
        src_uid=table.uid,
        dst_uid=dataset.uid,
        properties={},
        build_id=BUILD_ID,
    )
    with CanonicalPackageWriter(
        path,
        build_id=BUILD_ID,
        generated_at="2026-09-22T00:00:00+00:00",
    ) as writer:
        writer.write_vertex(dataset)
        writer.write_vertex(table)
        writer.write_edge(edge)
    return dataset, table, edge


def test_reader_verifies_and_reconstructs_package(tmp_path):
    expected_dataset, expected_table, expected_edge = _write_package(tmp_path / "cir")

    package = read_canonical_package(tmp_path / "cir")

    assert package.vertices == tuple(
        sorted((expected_dataset, expected_table), key=lambda item: (item.label, item.uid))
    )
    assert package.edges == (expected_edge,)
    assert package.manifest["build_id"] == BUILD_ID


def test_reader_rejects_modified_artifact(tmp_path):
    package_dir = tmp_path / "cir"
    _write_package(package_dir)
    artifact = package_dir / "vertices" / "dataset.jsonl"
    artifact.write_text(
        artifact.read_text(encoding="utf-8").replace('"one"', '"changed"'),
        encoding="utf-8",
    )

    with pytest.raises(PackageReadError, match="mismatch"):
        read_canonical_package(package_dir)


def test_reader_rejects_incomplete_package(tmp_path):
    package_dir = tmp_path / "cir"
    _write_package(package_dir)
    (package_dir / ".incomplete").write_text("simulated", encoding="utf-8")

    with pytest.raises(PackageReadError, match="incomplete"):
        read_canonical_package(package_dir)


def test_reader_rejects_wrong_schema_version(tmp_path):
    package_dir = tmp_path / "cir"
    _write_package(package_dir)
    manifest_path = package_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = "999"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(PackageReadError, match="schema version mismatch"):
        read_canonical_package(package_dir)
