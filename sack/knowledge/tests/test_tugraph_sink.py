import json

import pytest

from sack.knowledge.graph.model import EdgeRecord, VertexRecord
from sack.knowledge.graph.schema_registry import SCHEMA_VERSION
from sack.knowledge.graph.sinks.tugraph import (
    TuGraphExportError,
    build_tugraph_schema_config,
    export_tugraph_package,
)


BUILD_ID = "tugraph-test"


def _records():
    dataset = VertexRecord.from_uri(
        uri="http://sack.local/resource/dataset/one",
        label="Dataset",
        properties={"name": "one"},
        build_id=BUILD_ID,
    )
    table = VertexRecord.from_uri(
        uri="http://sack.local/resource/dataset/one/table/train",
        label="Table",
        properties={"name": ""},
        build_id=BUILD_ID,
    )
    relation = EdgeRecord.from_endpoints(
        edge_type="IS_PART_OF",
        src_uid=table.uid,
        dst_uid=dataset.uid,
        properties={},
        build_id=BUILD_ID,
    )
    return (dataset, table), (relation,)


def _all_files(root):
    return {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_schema_config_uses_uid_primary_and_edge_constraints():
    schemas = {item["label"]: item for item in build_tugraph_schema_config()}

    assert schemas["Dataset"]["primary"] == "uid"
    uid = next(
        item for item in schemas["Dataset"]["properties"] if item["name"] == "uid"
    )
    assert uid == {"name": "uid", "type": "STRING"}
    edge_uid = next(
        item for item in schemas["IS_PART_OF"]["properties"]
        if item["name"] == "edge_uid"
    )
    assert edge_uid["index"] is True
    assert "unique" not in edge_uid
    assert ["Column", "Table"] in schemas["IS_PART_OF"]["constraints"]
    assert ["Table", "Dataset"] in schemas["IS_PART_OF"]["constraints"]


def test_export_partitions_edges_by_endpoint_pair_and_preserves_empty_string(tmp_path):
    vertices, edges = _records()
    output = tmp_path / "tugraph"

    manifest = export_tugraph_package(
        vertices,
        edges,
        output,
        source_schema_version=SCHEMA_VERSION,
    )

    config = json.loads((output / "import.config.json").read_text(encoding="utf-8"))
    table_file = next(item for item in config["files"] if item["label"] == "Table")
    edge_file = next(item for item in config["files"] if item["label"] == "IS_PART_OF")
    assert table_file["format"] == "JSON"
    assert edge_file["SRC_ID"] == "Table"
    assert edge_file["DST_ID"] == "Dataset"
    assert edge_file["path"] == "edges/is_part_of__table__dataset.jsonl"
    assert edge_file["columns"][0] == "SRC_ID"
    assert edge_file["columns"][-1] == "DST_ID"

    table_row = json.loads((output / table_file["path"]).read_text(encoding="utf-8"))
    name_index = table_file["columns"].index("name")
    source_hash_index = table_file["columns"].index("source_hash")
    assert table_row[name_index] == ""
    assert table_row[source_hash_index] is None
    assert manifest.vertex_count == 2
    assert manifest.edge_count == 1
    assert (output / "manifest.json").is_file()
    report = json.loads((output / "validation_report.json").read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert report["edge_count_by_endpoint_pair"] == {"IS_PART_OF:Table->Dataset": 1}
    assert not (output / ".incomplete").exists()


def test_export_is_byte_deterministic(tmp_path):
    vertices, edges = _records()
    first = tmp_path / "first"
    second = tmp_path / "second"

    export_tugraph_package(
        reversed(vertices),
        edges,
        first,
        source_schema_version=SCHEMA_VERSION,
    )
    export_tugraph_package(
        vertices,
        reversed(edges),
        second,
        source_schema_version=SCHEMA_VERSION,
    )

    assert _all_files(first) == _all_files(second)


def test_export_refuses_to_overwrite_directory(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    vertices, edges = _records()

    with pytest.raises(TuGraphExportError, match="refusing to overwrite"):
        export_tugraph_package(
            vertices,
            edges,
            output,
            source_schema_version=SCHEMA_VERSION,
        )


def test_export_rejects_unknown_property(tmp_path):
    vertex = VertexRecord.from_uri(
        uri="http://sack.local/resource/dataset/unknown",
        label="Dataset",
        properties={"not_in_registry": "value"},
        build_id=BUILD_ID,
    )

    with pytest.raises(TuGraphExportError, match="unknown_property"):
        export_tugraph_package(
            (vertex,),
            (),
            tmp_path / "invalid",
            source_schema_version=SCHEMA_VERSION,
        )
