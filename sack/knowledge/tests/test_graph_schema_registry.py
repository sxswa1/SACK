import pytest

from sack.knowledge.graph.schema_registry import (
    EDGE_SCHEMAS,
    SCHEMA_VERSION,
    VERTEX_SCHEMAS,
    get_edge_schema,
    get_vertex_schema,
)


def test_registry_contains_migration_critical_labels():
    assert {"Dataset", "Table", "Column", "Pipeline", "Statement", "CoreInsight"} <= set(
        VERTEX_SCHEMAS
    )
    assert {
        "IS_PART_OF",
        "HAS_CONTENT_SIMILARITY",
        "HAS_LABEL_SIMILARITY",
        "HAS_PARAMETER",
        "HAS_CORE_INSIGHT",
        "IMPLEMENTED_IN",
    } <= set(EDGE_SCHEMAS)
    assert SCHEMA_VERSION


def test_rdf_star_edges_keep_their_required_property():
    similarity = get_edge_schema("HAS_CONTENT_SIMILARITY")
    parameter = get_edge_schema("HAS_PARAMETER")

    assert similarity.properties["certainty"].required
    assert "value" in parameter.properties
    assert parameter.scope_required


def test_is_part_of_uses_exact_endpoint_pairs():
    schema = get_edge_schema("IS_PART_OF")

    assert ("Column", "Table") in schema.endpoint_pairs
    assert ("Table", "Dataset") in schema.endpoint_pairs
    assert ("Column", "Dataset") not in schema.endpoint_pairs


def test_named_graph_replacement_edges_require_pipeline_scope():
    for label in (
        "NEXT_STATEMENT",
        "DATA_FLOW_TO",
        "CALLS_CLASS",
        "READS_TABLE",
        "HAS_PARAMETER",
        "HAS_CORE_INSIGHT",
        "IMPLEMENTED_IN",
    ):
        assert get_edge_schema(label).scope_required, label


def test_registry_is_read_only_and_unknown_labels_are_explicit():
    with pytest.raises(TypeError):
        VERTEX_SCHEMAS["Unknown"] = get_vertex_schema("Dataset")
    with pytest.raises(KeyError, match="Unknown edge label"):
        get_edge_schema("UNKNOWN")
