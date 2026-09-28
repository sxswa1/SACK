import pytest

from sack.knowledge.graph.merge import RecordMergeError, merge_graph_records
from sack.knowledge.graph.model import VertexRecord


BUILD_ID = "merge-test"
URI = "http://sack.local/resource/kaggle/titanic"


def make_vertex(properties, *, label="Dataset", build_id=BUILD_ID):
    return VertexRecord.from_uri(
        uri=URI,
        label=label,
        properties=properties,
        build_id=build_id,
    )


def test_sparse_and_rich_vertices_merge_without_losing_properties():
    sparse = make_vertex({"rdf_types_json": '["http://sack.local/ontology/Dataset"]'})
    rich = make_vertex({"name": "titanic", "overview": "Predict survival."})

    result = merge_graph_records(
        vertex_groups=[[sparse], [rich]],
        edge_groups=[],
    )

    assert len(result.vertices) == 1
    assert result.vertices[0].properties == {
        "rdf_types_json": '["http://sack.local/ontology/Dataset"]',
        "name": "titanic",
        "overview": "Predict survival.",
    }


def test_conflicting_vertex_property_fails_closed():
    first = make_vertex({"name": "titanic"})
    second = make_vertex({"name": "different"})

    with pytest.raises(RecordMergeError, match="Conflicting property"):
        merge_graph_records(vertex_groups=[[first], [second]], edge_groups=[])


def test_same_uid_with_different_label_is_identity_collision():
    dataset = make_vertex({})
    table = make_vertex({}, label="Table")

    with pytest.raises(RecordMergeError, match="identity collision"):
        merge_graph_records(vertex_groups=[[dataset], [table]], edge_groups=[])
