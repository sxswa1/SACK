import hashlib
import json

import pytest

from sack.knowledge.graph.model import EdgeRecord, VertexRecord
from sack.knowledge.graph.package_writer import CanonicalPackageWriter, PackageWriteError


BUILD_ID = "package-test"
GENERATED_AT = "2026-09-22T00:00:00+00:00"


def make_vertex(uri_suffix, label, **properties):
    return VertexRecord.from_uri(
        uri=f"http://sack.local/resource/{uri_suffix}",
        label=label,
        properties=properties,
        build_id=BUILD_ID,
    )


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_fixture_package(output_dir):
    dataset = make_vertex("kaggle/titanic", "Dataset", name="titanic")
    table = make_vertex("kaggle/titanic/train.csv", "Table", name="train.csv")
    relation = EdgeRecord.from_endpoints(
        edge_type="IS_PART_OF",
        src_uid=table.uid,
        dst_uid=dataset.uid,
        properties={},
        build_id=BUILD_ID,
    )

    with CanonicalPackageWriter(
        output_dir,
        build_id=BUILD_ID,
        generated_at=GENERATED_AT,
        metadata={"git_commit": "abc123", "source": "fixture"},
    ) as writer:
        # Sorting is per label, so different labels may be interleaved.
        writer.write_vertex(table)
        writer.write_vertex(dataset)
        writer.write_edge(relation)
    return dataset, table, relation


def test_writer_creates_label_files_and_verified_manifest(tmp_path):
    package = tmp_path / "package"
    write_fixture_package(package)

    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    artifacts = {item["relative_path"]: item for item in manifest["artifacts"]}

    assert manifest["build_id"] == BUILD_ID
    assert manifest["schema_version"]
    assert manifest["totals"]["vertex_count"] == 2
    assert manifest["totals"]["edge_count"] == 1
    assert set(artifacts) == {
        "vertices/dataset.jsonl",
        "vertices/table.jsonl",
        "edges/is_part_of.jsonl",
    }
    for relative_path, artifact in artifacts.items():
        path = package / relative_path
        assert artifact["sha256"] == file_digest(path)
        assert artifact["byte_count"] == len(path.read_bytes())
    assert not (package / ".incomplete").exists()


def test_same_input_produces_byte_identical_package(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    write_fixture_package(first)
    write_fixture_package(second)

    first_files = sorted(path.relative_to(first) for path in first.rglob("*") if path.is_file())
    second_files = sorted(path.relative_to(second) for path in second.rglob("*") if path.is_file())

    assert first_files == second_files
    for relative_path in first_files:
        assert (first / relative_path).read_bytes() == (second / relative_path).read_bytes()


def test_writer_rejects_duplicate_or_out_of_order_records(tmp_path):
    first = make_vertex("kaggle/first", "Dataset")
    second = make_vertex("kaggle/second", "Dataset")
    ordered = sorted([first, second], key=lambda item: item.uid)

    writer = CanonicalPackageWriter(
        tmp_path / "package",
        build_id=BUILD_ID,
        generated_at=GENERATED_AT,
    )
    writer.write_vertex(ordered[1])
    with pytest.raises(PackageWriteError, match="out-of-order"):
        writer.write_vertex(ordered[0])


def test_writer_rejects_build_mismatch(tmp_path):
    record = VertexRecord.from_uri(
        uri="http://sack.local/resource/kaggle/titanic",
        label="Dataset",
        properties={},
        build_id="another-build",
    )
    writer = CanonicalPackageWriter(
        tmp_path / "package",
        build_id=BUILD_ID,
        generated_at=GENERATED_AT,
    )

    with pytest.raises(PackageWriteError, match="does not match package"):
        writer.write_vertex(record)


def test_writer_never_overwrites_existing_directory(tmp_path):
    output_dir = tmp_path / "existing"
    output_dir.mkdir()
    (output_dir / "user-data.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(PackageWriteError, match="refusing to overwrite"):
        CanonicalPackageWriter(output_dir, build_id=BUILD_ID)

    assert (output_dir / "user-data.txt").read_text(encoding="utf-8") == "keep"


def test_failed_context_keeps_incomplete_marker(tmp_path):
    output_dir = tmp_path / "failed"

    with pytest.raises(RuntimeError):
        with CanonicalPackageWriter(output_dir, build_id=BUILD_ID):
            raise RuntimeError("simulated build failure")

    assert (output_dir / ".incomplete").exists()
    assert not (output_dir / "manifest.json").exists()
