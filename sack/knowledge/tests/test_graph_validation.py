from sack.knowledge.graph.model import EdgeRecord, VertexRecord
from sack.knowledge.graph.validation import validate_graph


BUILD_ID = "validation-test"


def vertex(uri_suffix, label, **properties):
    return VertexRecord.from_uri(
        uri=f"http://sack.local/resource/{uri_suffix}",
        label=label,
        properties=properties,
        build_id=BUILD_ID,
    )


def edge(edge_type, source, target, *, scope=None, **properties):
    return EdgeRecord.from_endpoints(
        edge_type=edge_type,
        src_uid=source.uid,
        dst_uid=target.uid,
        properties=properties,
        build_id=BUILD_ID,
        scope_uid=None if scope is None else scope.uid,
    )


def error_codes(report):
    return {issue.code for issue in report.errors}


def test_valid_pipeline_subgraph_passes():
    dataset = vertex("kaggle/titanic", "Dataset", name="titanic")
    pipeline = vertex("kaggle/titanic/p1", "Pipeline", title="baseline")
    statement = vertex(
        "kaggle/titanic/p1/s1",
        "Statement",
        ordinal=1,
        pipeline_uid=pipeline.uid,
    )
    function = vertex("library/pandas/read_csv", "Function", qualified_name="pandas.read_csv")
    edges = [
        edge("IS_PART_OF", pipeline, dataset),
        edge("IS_PART_OF", statement, pipeline),
        edge("CALLS_FUNCTION", statement, function, scope=pipeline),
    ]

    report = validate_graph([dataset, pipeline, statement, function], edges)

    assert report.is_valid
    assert report.vertex_count == 4
    assert report.edge_count == 3


def test_dangling_edge_is_rejected():
    dataset = vertex("kaggle/titanic", "Dataset")
    missing = vertex("kaggle/titanic/missing.csv", "Table")
    relation = edge("IS_PART_OF", missing, dataset)

    report = validate_graph([dataset], [relation])

    assert "missing_source_vertex" in error_codes(report)


def test_invalid_is_part_of_endpoint_pair_is_rejected():
    dataset = vertex("kaggle/titanic", "Dataset")
    column = vertex("kaggle/titanic/train.csv/age", "Column")

    report = validate_graph(
        [dataset, column],
        [edge("IS_PART_OF", column, dataset)],
    )

    assert "invalid_edge_endpoints" in error_codes(report)


def test_named_graph_edge_requires_pipeline_scope():
    statement = vertex("kaggle/titanic/p1/s1", "Statement")
    function = vertex("library/pandas/read_csv", "Function")

    report = validate_graph(
        [statement, function],
        [edge("CALLS_FUNCTION", statement, function)],
    )

    assert "missing_pipeline_scope" in error_codes(report)


def test_statement_and_edge_scope_must_match():
    pipeline_a = vertex("kaggle/titanic/p1", "Pipeline")
    pipeline_b = vertex("kaggle/titanic/p2", "Pipeline")
    statement = vertex(
        "kaggle/titanic/p1/s1",
        "Statement",
        pipeline_uid=pipeline_a.uid,
    )
    function = vertex("library/pandas/read_csv", "Function")

    report = validate_graph(
        [pipeline_a, pipeline_b, statement, function],
        [edge("CALLS_FUNCTION", statement, function, scope=pipeline_b)],
    )

    assert "statement_scope_mismatch" in error_codes(report)


def test_similarity_certainty_must_be_in_unit_interval():
    first = vertex("kaggle/a/t.csv/x", "Column")
    second = vertex("kaggle/b/t.csv/y", "Column")

    report = validate_graph(
        [first, second],
        [edge("HAS_CONTENT_SIMILARITY", first, second, certainty=1.2)],
    )

    assert "certainty_out_of_range" in error_codes(report)


def test_similarity_requires_reverse_edge_with_same_score():
    first = vertex("kaggle/a/t.csv/x", "Column")
    second = vertex("kaggle/b/t.csv/y", "Column")
    forward = edge("HAS_CONTENT_SIMILARITY", first, second, certainty=0.9)

    missing = validate_graph([first, second], [forward])
    assert "missing_reverse_similarity" in error_codes(missing)

    mismatch = validate_graph(
        [first, second],
        [forward, edge("HAS_CONTENT_SIMILARITY", second, first, certainty=0.8)],
    )
    assert "reverse_similarity_score_mismatch" in error_codes(mismatch)

    valid = validate_graph(
        [first, second],
        [forward, edge("HAS_CONTENT_SIMILARITY", second, first, certainty=0.9)],
    )
    assert valid.is_valid


def test_similarity_rejects_parallel_edges_for_one_directed_pair():
    first = vertex("kaggle/a/t.csv/x", "Column")
    second = vertex("kaggle/b/t.csv/y", "Column")
    forward = edge("HAS_LABEL_SIMILARITY", first, second, certainty=0.9)
    parallel = EdgeRecord.from_endpoints(
        edge_type="HAS_LABEL_SIMILARITY",
        src_uid=first.uid,
        dst_uid=second.uid,
        properties={"certainty": 0.9},
        build_id=BUILD_ID,
        discriminator="parallel",
    )
    reverse = edge("HAS_LABEL_SIMILARITY", second, first, certainty=0.9)

    report = validate_graph([first, second], [forward, parallel, reverse])

    assert "duplicate_similarity_pair" in error_codes(report)


def test_required_parameter_name_is_checked_by_registry():
    parameter = vertex("parameter/sep", "Parameter")

    report = validate_graph([parameter], [])

    assert "missing_required_property" in error_codes(report)
