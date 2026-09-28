import json

import pytest

from sack.knowledge.graph.builders.global_schema import (
    GlobalSchemaBuildError,
    build_global_schema_records,
    build_similarity_edges,
)
from sack.knowledge.graph.validation import validate_graph
from sack.knowledge.kg_governor.data_profiling.model.column_profile import ColumnProfile
from sack.knowledge.kg_governor.data_profiling.model.edainsight_profile import EDAInsightProfile


BUILD_ID = "global-schema-test"


def column(name, *, table="train.csv", table_path="/data/train.csv", true_ratio=None):
    return ColumnProfile(
        column_id=f"kaggle/titanic/{table}/{name}",
        dataset_name="titanic",
        dataset_id="kaggle/titanic",
        path=table_path,
        table_name=table,
        table_id=f"kaggle/titanic/{table}",
        column_name=name,
        data_source="kaggle",
        data_type="BOOLEAN" if true_ratio is not None else "INT",
        total_values=100,
        distinct_values_count=2 if true_ratio is not None else 80,
        missing_values_count=3,
        true_ratio=true_ratio,
        min_value=None if true_ratio is not None else 1,
        max_value=None if true_ratio is not None else 90,
        mean=None if true_ratio is not None else 30,
        median=None if true_ratio is not None else 28,
        iqr=None if true_ratio is not None else 20,
    )


def by_label(records, label):
    return [record for record in records if record.label == label]


def test_column_profiles_build_deduplicated_hierarchy_and_metadata():
    profiles = [column("Age"), column("Survived", true_ratio=0.38)]
    competition_profiles = {
        "kaggle/titanic": {
            "overview": "Predict survival.",
            "data_description": "Passenger table.",
            "structured_elements": {
                "problem_type": "classification",
                "domain": "transport",
                "data_type": ["tabular", "mixed"],
                "difficulty": "beginner",
            },
        }
    }

    result = build_global_schema_records(
        profiles,
        build_id=BUILD_ID,
        competition_profiles=competition_profiles,
    )

    assert len(by_label(result.vertices, "Source")) == 1
    assert len(by_label(result.vertices, "Dataset")) == 1
    assert len(by_label(result.vertices, "Table")) == 1
    assert len(by_label(result.vertices, "Column")) == 2
    assert len(result.edges) == 4

    dataset = by_label(result.vertices, "Dataset")[0]
    assert dataset.properties["problem_type"] == "classification"
    assert dataset.properties["data_type"] == '["tabular", "mixed"]'
    assert "overview_embedding" not in dataset.properties

    age = next(record for record in by_label(result.vertices, "Column") if record.properties["name"] == "Age")
    assert age.properties["total_count"] == 100
    assert age.properties["median"] == 28.0

    report = validate_graph(result.vertices, result.edges)
    assert report.is_valid, report.errors


def test_eda_profile_is_preserved_as_versionable_json_payload():
    profile = column("Age")
    eda = EDAInsightProfile(
        eda_id="kaggle/titanic_pre_eda",
        competition_id="kaggle/titanic",
        eda_type="pre_eda",
        pre_eda_data_quality={"missingness": {"overall_missing_rate": 0.03}},
    )

    result = build_global_schema_records(
        [profile],
        build_id=BUILD_ID,
        eda_profiles={"kaggle/titanic": [eda]},
    )

    insight = by_label(result.vertices, "PreliminaryEDAInsight")[0]
    payload = json.loads(insight.properties["payload_json"])
    assert payload["pre_eda_data_quality"]["missingness"]["overall_missing_rate"] == 0.03
    assert any(edge.edge_type == "HAS_PRELIMINARY_EDA_INSIGHT" for edge in result.edges)
    assert validate_graph(result.vertices, result.edges).is_valid


def test_similarity_mapping_keeps_current_forward_and_reverse_edges():
    first = column("Survived", table="train.csv", true_ratio=0.38)
    second = column("Outcome", table="test.csv", table_path="/data/test.csv", true_ratio=0.4)

    forward, reverse = build_similarity_edges(
        first,
        second,
        edge_type="HAS_CONTENT_SIMILARITY",
        certainty=0.98,
        build_id=BUILD_ID,
    )

    assert forward.src_uid == reverse.dst_uid
    assert forward.dst_uid == reverse.src_uid
    assert forward.properties["certainty"] == reverse.properties["certainty"] == 0.98
    assert forward.edge_uid != reverse.edge_uid


def test_conflicting_table_metadata_is_not_silently_overwritten():
    profiles = [
        column("Age", table_path="/data/first.csv"),
        column("Survived", table_path="/data/second.csv", true_ratio=0.38),
    ]

    with pytest.raises(GlobalSchemaBuildError, match="Conflicting records for vertex"):
        build_global_schema_records(profiles, build_id=BUILD_ID)


@pytest.mark.parametrize("certainty", [-0.1, 1.1, float("nan")])
def test_similarity_rejects_invalid_certainty(certainty):
    with pytest.raises(GlobalSchemaBuildError):
        build_similarity_edges(
            column("A"),
            column("B", table="other.csv", table_path="/data/other.csv"),
            edge_type="HAS_LABEL_SIMILARITY",
            certainty=certainty,
            build_id=BUILD_ID,
        )
