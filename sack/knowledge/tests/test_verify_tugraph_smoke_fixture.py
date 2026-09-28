import json

import pandas as pd
import pytest

from sack.knowledge.migration.build_tugraph_smoke_fixture import (
    SMOKE_DATASET_URI,
    SMOKE_COLUMN_URI,
    SMOKE_INSIGHT_URI,
    SMOKE_OTHER_DATASET_URI,
    SMOKE_OTHER_COLUMN_URI,
    SMOKE_OVERVIEW,
    SMOKE_PIPELINE_URI,
    SMOKE_STATEMENT_TWO_TEXT,
    SMOKE_TABLE_URI,
)
from sack.knowledge.migration.verify_tugraph_smoke_fixture import (
    TuGraphSmokeVerificationError,
    verify_tugraph_smoke_fixture,
)


class FakeSmokeStore:
    def __init__(self, *, wrong_name=False):
        self.wrong_name = wrong_name
        self.closed = False

    def healthcheck(self):
        return True

    def get_top_pipelines(self, dataset_uri, k):
        return pd.DataFrame(
            [
                {
                    "Pipeline_id": SMOKE_PIPELINE_URI,
                    "Pipeline": "smoke pipeline",
                    "Score": 0.875,
                }
            ]
        )

    def find_candidate_competitions(self, problem_type, data_type, exclude_uri):
        return [SMOKE_OTHER_DATASET_URI]

    def list_competitions(self):
        return [
            {"comp_uri": SMOKE_OTHER_DATASET_URI},
            {"comp_uri": SMOKE_DATASET_URI},
        ]

    def get_competition_name(self, competition_uri):
        return "wrong" if self.wrong_name else "冒烟竞赛"

    def get_competition_tables(self, competition_uri):
        return [
            {
                "table_uri": SMOKE_TABLE_URI,
                "table_name": "train.csv",
                "columns": [{"col_name": "feature_a"}],
            }
        ]

    def get_column_similarities(self, column_uri, relation):
        target_uri = (
            SMOKE_OTHER_COLUMN_URI
            if column_uri == SMOKE_COLUMN_URI
            else SMOKE_COLUMN_URI
        )
        certainty = 0.875 if relation == "HAS_CONTENT_SIMILARITY" else 0.625
        return [{"target_uri": target_uri, "certainty": certainty}]

    def get_competition_field(self, competition_uri, field):
        return SMOKE_OVERVIEW

    def get_eda_insight(self, competition_uri, eda_type):
        if eda_type == "deep_eda":
            return {
                "special_scenarios": {"temporal_properties.is_time_series": False},
            }
        return {
            "data_quality": {"missingness.overall_missing_rate": 0.1},
            "basic_dimensionality": {"samples_per_feature": 10.0},
        }

    def get_core_insights(self, pipeline_uri):
        return pd.DataFrame(
            [{"Insight_ID": "CI-1", "Spanning_Phases": "Model Building"}]
        )

    def get_insight_code(self, insight_uri):
        assert insight_uri == SMOKE_INSIGHT_URI
        return [
            {
                "stmt_uri": f"{SMOKE_PIPELINE_URI}/s2",
                "code_text": SMOKE_STATEMENT_TWO_TEXT,
                "order": 2,
            }
        ]

    def close(self):
        self.closed = True


def test_smoke_verifier_exercises_all_p0_contracts(tmp_path):
    store = FakeSmokeStore()

    report = verify_tugraph_smoke_fixture(
        result_dir=tmp_path / "results",
        store=store,
        environ={"SACK_TUGRAPH_GRAPH": "smoke"},
    )

    assert report["status"] == "passed"
    assert report["graph"] == "smoke"
    assert len(report["checks"]) == 13
    assert not store.closed


def test_smoke_verifier_records_domain_mismatch(tmp_path):
    result_dir = tmp_path / "results"

    with pytest.raises(TuGraphSmokeVerificationError, match="failed 1 checks"):
        verify_tugraph_smoke_fixture(
            result_dir=result_dir,
            store=FakeSmokeStore(wrong_name=True),
        )

    report = json.loads(
        (result_dir / "smoke_verification_report.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "failed"
    failed = [item for item in report["checks"] if item["status"] == "failed"]
    assert failed[0]["name"] == "competition-name"


def test_smoke_verifier_refuses_existing_result_dir(tmp_path):
    result_dir = tmp_path / "results"
    result_dir.mkdir()

    with pytest.raises(TuGraphSmokeVerificationError, match="refusing to overwrite"):
        verify_tugraph_smoke_fixture(
            result_dir=result_dir,
            store=FakeSmokeStore(),
        )
