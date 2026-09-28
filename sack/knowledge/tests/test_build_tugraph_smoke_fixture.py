import json

from sack.knowledge.graph.schema_registry import SCHEMA_VERSION
from sack.knowledge.graph.validation import validate_graph
from sack.knowledge.migration.build_tugraph_smoke_fixture import (
    SMOKE_BUILD_ID,
    build_smoke_records,
    build_tugraph_smoke_fixture,
)
from sack.knowledge.migration.load_tugraph import verify_tugraph_package


def test_smoke_records_cover_p0_shapes_and_special_strings():
    vertices, edges = build_smoke_records()

    report = validate_graph(vertices, edges)
    assert report.is_valid
    assert len(vertices) == 16
    assert len(edges) == 24
    assert {vertex.label for vertex in vertices} >= {
        "Column",
        "CoreInsight",
        "Dataset",
        "InDepthEDAInsight",
        "Pipeline",
        "PreliminaryEDAInsight",
        "Statement",
        "Table",
    }
    assert any("中文" in str(vertex.properties) for vertex in vertices)
    assert any("\\n" in str(vertex.properties) for vertex in vertices)
    assert all(
        edge.scope_uid is not None
        for edge in edges
        if edge.edge_type
        in {
            "CALLS_FUNCTION",
            "DATA_FLOW_TO",
            "HAS_CORE_INSIGHT",
            "HAS_PARAMETER",
            "IMPLEMENTED_IN",
            "NEXT_STATEMENT",
            "READS_COLUMN",
            "READS_TABLE",
        }
    )


def test_smoke_fixture_is_a_verified_tugraph_package(tmp_path):
    output = tmp_path / "smoke-package"

    manifest = build_tugraph_smoke_fixture(output)
    verified = verify_tugraph_package(output)

    assert manifest.build_id == SMOKE_BUILD_ID
    assert manifest.source_schema_version == SCHEMA_VERSION
    assert verified["build_id"] == SMOKE_BUILD_ID
    preflight = json.loads(
        (output / "validation_report.json").read_text(encoding="utf-8")
    )
    assert preflight["status"] == "passed"
    assert preflight["totals"] == {
        "edge_count": 24,
        "error_count": 0,
        "vertex_count": 16,
        "warning_count": 0,
    }

    statement_rows = list((output / "vertices" / "statement.jsonl").open())
    assert "中文注释" in "".join(statement_rows)
    assert "\\n" in "".join(statement_rows)
