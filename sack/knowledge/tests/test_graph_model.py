import json

import pytest

from sack.knowledge.graph.id_codec import vertex_uid
from sack.knowledge.graph.model import (
    EdgeRecord,
    RecordValidationError,
    VertexRecord,
    record_json,
)


BUILD_ID = "test-build-001"


def test_vertex_from_uri_preserves_uri_and_has_stable_json():
    vertex = VertexRecord.from_uri(
        uri="http://sack.local/resource/kaggle/titanic",
        label="Dataset",
        properties={"name": "titanic", "tags": ("tabular", "binary")},
        build_id=BUILD_ID,
    )

    assert vertex.uid == vertex_uid(vertex.uri)
    assert vertex.properties["tags"] == ["tabular", "binary"]
    assert json.loads(record_json(vertex))["name"] == "titanic"
    assert record_json(vertex) == record_json(vertex)


def test_vertex_rejects_uid_that_does_not_match_uri():
    with pytest.raises(RecordValidationError, match="does not match canonical URI"):
        VertexRecord(
            uid="0" * 64,
            uri="http://sack.local/resource/kaggle/titanic",
            label="Dataset",
            properties={},
            build_id=BUILD_ID,
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_vertex_rejects_nonfinite_properties(value):
    with pytest.raises(RecordValidationError, match="NaN or infinity"):
        VertexRecord.from_uri(
            uri="http://sack.local/resource/kaggle/titanic",
            label="Dataset",
            properties={"score": value},
            build_id=BUILD_ID,
        )


def test_reserved_property_cannot_shadow_record_identity():
    with pytest.raises(RecordValidationError, match="reserved"):
        VertexRecord.from_uri(
            uri="http://sack.local/resource/kaggle/titanic",
            label="Dataset",
            properties={"uid": "different"},
            build_id=BUILD_ID,
        )


def test_edge_factory_is_deterministic_and_keeps_scope():
    statement_uid = vertex_uid(
        "http://sack.local/resource/kaggle/titanic/pipeline/s1"
    )
    parameter_uid = vertex_uid("http://sack.local/resource/parameter/sep")
    pipeline_uid = vertex_uid("http://sack.local/resource/kaggle/titanic/pipeline")

    first = EdgeRecord.from_endpoints(
        edge_type="HAS_PARAMETER",
        src_uid=statement_uid,
        dst_uid=parameter_uid,
        properties={"value": ",", "value_type": "string"},
        build_id=BUILD_ID,
        scope_uid=pipeline_uid,
        discriminator="sep",
    )
    second = EdgeRecord.from_endpoints(
        edge_type="HAS_PARAMETER",
        src_uid=statement_uid,
        dst_uid=parameter_uid,
        properties={"value": ";", "value_type": "string"},
        build_id=BUILD_ID,
        scope_uid=pipeline_uid,
        discriminator="sep",
    )

    assert first.edge_uid == second.edge_uid
    assert first.scope_uid == pipeline_uid
    assert first.to_dict()["value"] == ","


def test_mutable_similarity_score_is_not_part_of_edge_identity():
    source = vertex_uid("http://sack.local/resource/kaggle/a/table/x")
    target = vertex_uid("http://sack.local/resource/kaggle/b/table/y")

    low = EdgeRecord.from_endpoints(
        edge_type="HAS_CONTENT_SIMILARITY",
        src_uid=source,
        dst_uid=target,
        properties={"certainty": 0.75},
        build_id=BUILD_ID,
    )
    high = EdgeRecord.from_endpoints(
        edge_type="HAS_CONTENT_SIMILARITY",
        src_uid=source,
        dst_uid=target,
        properties={"certainty": 0.95},
        build_id=BUILD_ID,
    )

    assert low.edge_uid == high.edge_uid
    assert low.properties != high.properties
