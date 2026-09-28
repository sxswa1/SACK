import json

import pytest

from sack.knowledge.graph.model import EdgeRecord, VertexRecord
from sack.knowledge.graph.schema_registry import SCHEMA_VERSION
from sack.knowledge.graph.sinks.tugraph import export_tugraph_package
from sack.knowledge.migration.validate_tugraph import (
    TuGraphValidationError,
    validate_loaded_tugraph,
)


class FakeClient:
    def __init__(self, counts):
        self.counts = list(counts)
        self.queries = []

    def run(self, query, parameters=None):
        self.queries.append((query, parameters))
        return [{"count": self.counts.pop(0)}]

    def close(self):
        raise AssertionError("Injected clients must not be closed")


def _package(tmp_path):
    dataset = VertexRecord.from_uri(
        uri="http://sack.local/resource/kaggle/validation",
        label="Dataset",
        properties={"name": "validation"},
        build_id="post-import-test",
    )
    table = VertexRecord.from_uri(
        uri=f"{dataset.uri}/train.csv",
        label="Table",
        properties={"name": "train.csv"},
        build_id="post-import-test",
    )
    edge = EdgeRecord.from_endpoints(
        edge_type="IS_PART_OF",
        src_uid=table.uid,
        dst_uid=dataset.uid,
        properties={},
        build_id="post-import-test",
    )
    package = tmp_path / "package"
    export_tugraph_package(
        (dataset, table),
        (edge,),
        package,
        source_schema_version=SCHEMA_VERSION,
    )
    return package


def test_post_import_validator_checks_labels_edges_and_endpoint_pairs(tmp_path):
    package = _package(tmp_path)
    client = FakeClient([1, 1, 1, 1])

    report = validate_loaded_tugraph(
        package_dir=package,
        result_dir=tmp_path / "results",
        client=client,
    )

    assert report["status"] == "passed"
    assert [item["name"] for item in report["checks"]] == [
        "vertex:Dataset",
        "vertex:Table",
        "edge:IS_PART_OF",
        "endpoint:IS_PART_OF:Table->Dataset",
    ]
    assert all(parameters == {} for _, parameters in client.queries)


def test_post_import_validator_records_mismatch_before_raising(tmp_path):
    package = _package(tmp_path)
    result_dir = tmp_path / "results"

    with pytest.raises(TuGraphValidationError, match="failed 1 checks"):
        validate_loaded_tugraph(
            package_dir=package,
            result_dir=result_dir,
            client=FakeClient([1, 0, 1, 1]),
        )

    report = json.loads(
        (result_dir / "post_import_validation.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "failed"
    assert report["failed_check_count"] == 1


def test_post_import_validator_checks_named_graph_scope(tmp_path):
    build_id = "scope-post-import"
    pipeline = VertexRecord.from_uri(
        uri="http://sack.local/resource/kaggle/validation/pipeline",
        label="Pipeline",
        properties={"title": "pipeline"},
        build_id=build_id,
    )
    statement = VertexRecord.from_uri(
        uri=f"{pipeline.uri}/s1",
        label="Statement",
        properties={"ordinal": 1, "pipeline_uid": pipeline.uid},
        build_id=build_id,
    )
    function = VertexRecord.from_uri(
        uri="http://sack.local/resource/library/pandas/read_csv",
        label="Function",
        properties={"qualified_name": "pandas.read_csv"},
        build_id=build_id,
    )
    edge = EdgeRecord.from_endpoints(
        edge_type="CALLS_FUNCTION",
        src_uid=statement.uid,
        dst_uid=function.uid,
        properties={},
        build_id=build_id,
        scope_uid=pipeline.uid,
    )
    package = tmp_path / "scope-package"
    export_tugraph_package(
        (pipeline, statement, function),
        (edge,),
        package,
        source_schema_version=SCHEMA_VERSION,
    )
    client = FakeClient([1, 1, 1, 1, 1, 0, 0])

    report = validate_loaded_tugraph(
        package_dir=package,
        result_dir=tmp_path / "scope-results",
        client=client,
    )

    names = [item["name"] for item in report["checks"]]
    assert "scope-present:CALLS_FUNCTION" in names
    assert "source-statement-scope:CALLS_FUNCTION" in names
