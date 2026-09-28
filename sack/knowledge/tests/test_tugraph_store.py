import json

import pytest

from sack.knowledge.graph.id_codec import vertex_uid
from sack.knowledge.stores.tugraph import TuGraphGraphStore, TuGraphStoreError


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.closed = False

    def run(self, query, parameters=None):
        self.calls.append((query, parameters))
        return self.responses.pop(0)

    def close(self):
        self.closed = True


def test_top_pipelines_is_parameterized_and_has_legacy_columns():
    dataset_uri = "http://sack.local/resource/kaggle/example"
    client = FakeClient(
        [[{
            "Pipeline_id": f"{dataset_uri}/pipeline",
            "Pipeline": "best",
            "Author": "author",
            "Written_on": "2024-01-01",
            "Number_of_votes": 3,
            "Score": 0.9,
        }]]
    )
    store = TuGraphGraphStore(client)

    result = store.get_top_pipelines(dataset_uri, 3)

    query, parameters = client.calls[0]
    assert dataset_uri not in query
    assert parameters == {"dataset_uid": vertex_uid(dataset_uri), "row_limit": 3}
    assert "$dataset_uid" in query
    assert "$row_limit" in query
    assert list(result.columns) == [
        "Pipeline_id",
        "Pipeline",
        "Author",
        "Written_on",
        "Number_of_votes",
        "Score",
    ]


def test_top_pipelines_without_dataset_has_valid_where_clause():
    client = FakeClient([[]])

    result = TuGraphGraphStore(client).get_top_pipelines(None, None)

    query, parameters = client.calls[0]
    assert "WHERE p.title IS NOT NULL" in query
    assert "\nAND p.title" not in query
    assert parameters == {}
    assert result.empty


def test_core_insights_normalizes_spanning_phases_and_columns():
    pipeline_uri = "http://sack.local/resource/kaggle/example/pipeline"
    client = FakeClient(
        [[{
            "insight_uid": "insight-uid",
            "Insight_ID": "i1",
            "Description": "desc",
            "Insight_Type": "cleaning",
            "Effectiveness": "works",
            "Evidence": "metric",
            "Phase": "Data Cleaning",
        }], [
            {"insight_uid": "insight-uid", "phase_name": "Model Building"},
            {"insight_uid": "insight-uid", "phase_name": "Data Cleaning"},
            {"insight_uid": "insight-uid", "phase_name": "Data Cleaning"},
        ]]
    )
    result = TuGraphGraphStore(client).get_core_insights(pipeline_uri)

    assert result.iloc[0]["Spanning_Phases"] == "Data Cleaning, Model Building"
    assert client.calls[0][1] == {"pipeline_uid": vertex_uid(pipeline_uri)}
    assert client.calls[1][1] == {"insight_uids": ["insight-uid"]}


def test_candidate_competitions_are_parameterized():
    excluded = "http://sack.local/resource/kaggle/current"
    client = FakeClient([[{"competition_uri": "http://sack.local/resource/kaggle/other"}]])

    result = TuGraphGraphStore(client).find_candidate_competitions(
        "classification",
        "tabular",
        excluded,
    )

    query, parameters = client.calls[0]
    assert excluded not in query
    assert result == ["http://sack.local/resource/kaggle/other"]
    assert parameters == {
        "data_type": "tabular",
        "exclude_uid": vertex_uid(excluded),
        "problem_type": "classification",
    }


def test_similarity_reads_certainty_in_both_directions_with_relation_whitelist():
    source = "http://sack.local/resource/kaggle/example/train.csv/a"
    target = "http://sack.local/resource/kaggle/example/train.csv/b"
    client = FakeClient([[{"target_uri": target, "certainty": 0.875}]])
    store = TuGraphGraphStore(client)

    assert store.get_column_similarities(source, "HAS_CONTENT_SIMILARITY") == [
        {"target_uri": target, "certainty": 0.875}
    ]
    query, parameters = client.calls[0]
    assert "HAS_CONTENT_SIMILARITY" in query
    assert source not in query
    assert parameters == {"column_uid": vertex_uid(source)}
    with pytest.raises(ValueError, match="Unsupported similarity relation"):
        store.get_column_similarities(source, "BAD_RELATION")


def test_list_competitions_preserves_legacy_keys():
    client = FakeClient([[{
        "comp_uri": "http://sack.local/resource/kaggle/one",
        "comp_name": "one",
        "problem_type": " classification ",
        "data_type": " tabular ",
    }]])

    result = TuGraphGraphStore(client).list_competitions()

    assert result == [{
        "comp_uri": "http://sack.local/resource/kaggle/one",
        "comp_name": "one",
        "problem_type": "classification",
        "data_type": "tabular",
    }]


def test_competition_tables_are_grouped_deterministically():
    uri = "http://sack.local/resource/kaggle/one"
    client = FakeClient([[{
        "table_uid": "t",
        "table_uri": f"{uri}/train.csv",
        "table_name": "train.csv",
        "column_uid": "c",
        "col_uri": f"{uri}/train.csv/age",
        "col_name": "age",
        "data_type": "int",
    }]])

    result = TuGraphGraphStore(client).get_competition_tables(uri)

    assert result == [{
        "table_uri": f"{uri}/train.csv",
        "table_name": "train.csv",
        "columns": [{
            "col_uri": f"{uri}/train.csv/age",
            "col_name": "age",
            "data_type": "int",
        }],
    }]
    assert client.calls[0][1] == {"dataset_uid": vertex_uid(uri)}


def test_eda_payload_is_mapped_to_existing_module_shape():
    uri = "http://sack.local/resource/kaggle/one"
    payload = {
        "eda_type": "pre_eda",
        "pre_eda_data_quality": {"missingness": {"overall_missing_rate": 0.1}},
        "pre_eda_basic_distribution": {
            "numerical": {"skewness_profile": {"highly_skewed_ratio": 0.2}}
        },
        "pre_eda_basic_dimensionality": {"samples_per_feature": 20.0},
    }
    client = FakeClient([[{"payload_json": json.dumps(payload)}]])

    result = TuGraphGraphStore(client).get_eda_insight(uri, "pre_eda")

    assert result == {
        "data_quality": {"missingness.overall_missing_rate": 0.1},
        "basic_distribution": {"numerical.skewness_profile.highly_skewed_ratio": 0.2},
        "basic_dimensionality": {"samples_per_feature": 20.0},
    }


def test_competition_field_uses_whitelist_and_parameter():
    uri = "http://sack.local/resource/kaggle/example"
    client = FakeClient([[{"field_value": "classification"}]])
    store = TuGraphGraphStore(client)

    assert store.get_competition_field(uri, "problem_type") == "classification"
    query, parameters = client.calls[0]
    assert uri not in query
    assert "d.problem_type" in query
    assert parameters == {"dataset_uid": vertex_uid(uri)}

    with pytest.raises(ValueError, match="Unsupported"):
        store.get_competition_field(uri, "uid MATCH (n)")


def test_insight_code_is_ordered_domain_data():
    uri = "http://sack.local/resource/kaggle/example/pipeline/insight/i1"
    client = FakeClient(
        [[{
            "stmt_uri": "http://sack.local/resource/kaggle/example/pipeline/s2",
            "code_text": "fit()",
            "statement_order": 2,
        }]]
    )

    result = TuGraphGraphStore(client).get_insight_code(uri)

    assert result == [{
        "stmt_uri": "http://sack.local/resource/kaggle/example/pipeline/s2",
        "code_text": "fit()",
        "order": 2,
    }]
    assert client.calls[0][1] == {"insight_uid": vertex_uid(uri)}


def test_insight_code_rejects_invalid_order():
    client = FakeClient([[{"stmt_uri": "u", "code_text": "x", "statement_order": "2"}]])

    with pytest.raises(TuGraphStoreError, match="order"):
        TuGraphGraphStore(client).get_insight_code(
            "http://sack.local/resource/kaggle/example/pipeline/insight/i1"
        )


def test_healthcheck_and_close():
    client = FakeClient([[{"ok": 1}]])
    store = TuGraphGraphStore(client)

    assert store.healthcheck()
    store.close()
    assert client.closed
