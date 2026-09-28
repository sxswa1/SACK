import json

import pytest

from sack.knowledge.kg_governor.data_profiling.model.column_profile import ColumnProfile
from sack.knowledge.kg_governor.data_profiling.model.competition_profile import CompetitionProfile
from sack.knowledge.kg_governor.data_profiling.model.edainsight_profile import EDAInsightProfile
from sack.knowledge.migration.build_profile_cir import (
    ProfilePackageBuildError,
    build_profile_package,
    load_profiles,
)


def save_fixture_profiles(base_dir):
    ColumnProfile(
        column_id="kaggle/titanic/train.csv/Age",
        dataset_name="titanic",
        dataset_id="kaggle/titanic",
        path="/data/train.csv",
        table_name="train.csv",
        table_id="kaggle/titanic/train.csv",
        column_name="Age",
        data_source="kaggle",
        data_type="INT",
        total_values=100,
        distinct_values_count=80,
        missing_values_count=3,
        min_value=1,
        max_value=90,
        mean=30,
        median=28,
        iqr=20,
        embedding=[0.1, 0.2],
        embedding_scaling_factor=0.4,
    ).save_profile(base_dir)
    CompetitionProfile(
        competition_id="kaggle/titanic",
        competition_name="titanic",
        data_source="kaggle",
        overview="Predict survival.",
        data_description="Passenger records.",
        overview_embedding=[0.3, 0.4],
        data_description_embedding=[0.5, 0.6],
        structured_elements={"problem_type": "classification"},
    ).save_profile(base_dir / "competition_profiles")
    EDAInsightProfile(
        eda_id="kaggle/titanic_pre_eda",
        competition_id="kaggle/titanic",
        eda_type="pre_eda",
        pre_eda_data_quality={"missingness": {"overall_missing_rate": 0.03}},
    ).save_profile(base_dir / "eda_insight_profiles")


def test_profile_directory_builds_a_valid_partial_package(tmp_path):
    profiles_dir = tmp_path / "profiles"
    save_fixture_profiles(profiles_dir)
    output_dir = tmp_path / "canonical"

    manifest = build_profile_package(
        profiles_dir=profiles_dir,
        output_dir=output_dir,
        build_id="fixture-build",
        generated_at="2026-09-22T00:00:00+00:00",
    )

    manifest_data = manifest.to_dict()
    assert manifest_data["totals"] == {
        "byte_count": manifest_data["totals"]["byte_count"],
        "edge_count": 4,
        "vertex_count": 5,
    }
    assert manifest_data["metadata"]["includes_similarity_edges"] is False
    assert manifest_data["metadata"]["includes_pipeline_graph"] is False
    assert (output_dir / "vertices" / "column.jsonl").exists()
    assert (output_dir / "vertices" / "preliminary_eda_insight.jsonl").exists()

    column = json.loads(
        (output_dir / "vertices" / "column.jsonl").read_text(encoding="utf-8")
    )
    assert "embedding" not in column


def test_load_profiles_requires_at_least_one_column_profile(tmp_path):
    profiles_dir = tmp_path / "empty"
    profiles_dir.mkdir()

    with pytest.raises(ProfilePackageBuildError, match="No column profiles"):
        load_profiles(profiles_dir)
