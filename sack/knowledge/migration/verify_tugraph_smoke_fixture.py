"""Verify Agent P0 query contracts against the imported smoke fixture."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sack.knowledge.clients.tugraph_bolt import TuGraphBoltClient
from sack.knowledge.migration.build_tugraph_smoke_fixture import (
    SMOKE_BUILD_ID,
    SMOKE_DATASET_URI,
    SMOKE_INSIGHT_URI,
    SMOKE_OTHER_DATASET_URI,
    SMOKE_COLUMN_URI,
    SMOKE_OTHER_COLUMN_URI,
    SMOKE_OVERVIEW,
    SMOKE_PIPELINE_URI,
    SMOKE_STATEMENT_TWO_TEXT,
    SMOKE_TABLE_URI,
)
from sack.knowledge.stores.tugraph import TuGraphGraphStore


class TuGraphSmokeVerificationError(RuntimeError):
    """Raised when an imported smoke fixture violates a P0 contract."""


def _assert_equal(actual: Any, expected: Any) -> None:
    if actual != expected:
        raise AssertionError(f"expected {expected!r}, got {actual!r}")


def verify_tugraph_smoke_fixture(
    *,
    result_dir: str | Path,
    store: Any | None = None,
    environ: Mapping[str, str] | None = None,
) -> Mapping[str, Any]:
    """Exercise every migrated Agent P0 domain query against known data."""

    values = os.environ if environ is None else environ
    owned_store = store is None
    if store is None:
        password = values.get("SACK_TUGRAPH_PASSWORD")
        if not password:
            raise TuGraphSmokeVerificationError("SACK_TUGRAPH_PASSWORD is required")
        client = TuGraphBoltClient(
            uri=values.get("SACK_TUGRAPH_BOLT_URL", "bolt://127.0.0.1:7687"),
            graph=values.get("SACK_TUGRAPH_GRAPH", "sack_poc"),
            user=values.get("SACK_TUGRAPH_USER", "admin"),
            password=password,
        )
        store = TuGraphGraphStore(client)

    output_root = Path(result_dir).resolve()
    try:
        output_root.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        if owned_store:
            store.close()
        raise TuGraphSmokeVerificationError(
            f"Result directory already exists; refusing to overwrite: {output_root}"
        ) from exc

    checks: list[dict[str, Any]] = []

    def check(name: str, operation: Callable[[], None]) -> None:
        try:
            operation()
        except Exception as exc:
            checks.append(
                {
                    "error": f"{type(exc).__name__}: {exc}",
                    "name": name,
                    "status": "failed",
                }
            )
        else:
            checks.append({"name": name, "status": "passed"})

    try:
        check("healthcheck", lambda: _assert_equal(store.healthcheck(), True))

        def top_pipeline() -> None:
            rows = store.get_top_pipelines(SMOKE_DATASET_URI, 3).to_dict("records")
            _assert_equal(len(rows), 1)
            _assert_equal(rows[0]["Pipeline_id"], SMOKE_PIPELINE_URI)
            _assert_equal(rows[0]["Pipeline"], "smoke pipeline")
            _assert_equal(rows[0]["Score"], 0.875)

        check("top-pipelines", top_pipeline)
        check(
            "candidate-competitions",
            lambda: _assert_equal(
                store.find_candidate_competitions(
                    "classification", "tabular", SMOKE_DATASET_URI
                ),
                [SMOKE_OTHER_DATASET_URI],
            ),
        )

        def competitions() -> None:
            uris = sorted(item["comp_uri"] for item in store.list_competitions())
            _assert_equal(
                uris,
                sorted([SMOKE_DATASET_URI, SMOKE_OTHER_DATASET_URI]),
            )

        check("list-competitions", competitions)
        check(
            "competition-name",
            lambda: _assert_equal(
                store.get_competition_name(SMOKE_DATASET_URI), "冒烟竞赛"
            ),
        )

        def competition_tables() -> None:
            tables = store.get_competition_tables(SMOKE_DATASET_URI)
            _assert_equal(len(tables), 1)
            _assert_equal(tables[0]["table_uri"], SMOKE_TABLE_URI)
            _assert_equal(tables[0]["table_name"], "train.csv")
            _assert_equal(tables[0]["columns"][0]["col_name"], "feature_a")

        check("competition-tables", competition_tables)

        def similarity_edges(relation: str, expected: float) -> None:
            _assert_equal(
                store.get_column_similarities(SMOKE_COLUMN_URI, relation),
                [{"target_uri": SMOKE_OTHER_COLUMN_URI, "certainty": expected}],
            )
            _assert_equal(
                store.get_column_similarities(SMOKE_OTHER_COLUMN_URI, relation),
                [{"target_uri": SMOKE_COLUMN_URI, "certainty": expected}],
            )

        check(
            "rdf-star-content-certainty-and-reverse",
            lambda: similarity_edges("HAS_CONTENT_SIMILARITY", 0.875),
        )
        check(
            "rdf-star-label-certainty-and-reverse",
            lambda: similarity_edges("HAS_LABEL_SIMILARITY", 0.625),
        )
        check(
            "competition-field-unicode-newline",
            lambda: _assert_equal(
                store.get_competition_field(SMOKE_DATASET_URI, "overview"),
                SMOKE_OVERVIEW,
            ),
        )

        def preliminary_eda() -> None:
            value = store.get_eda_insight(SMOKE_DATASET_URI, "pre_eda")
            _assert_equal(
                value["data_quality"],
                {"missingness.overall_missing_rate": 0.1},
            )
            _assert_equal(
                value["basic_dimensionality"],
                {"samples_per_feature": 10.0},
            )

        check("preliminary-eda-json", preliminary_eda)

        def in_depth_eda() -> None:
            value = store.get_eda_insight(SMOKE_DATASET_URI, "deep_eda")
            _assert_equal(
                value["special_scenarios"],
                {"temporal_properties.is_time_series": False},
            )

        check("in-depth-eda-json", in_depth_eda)

        def core_insights() -> None:
            rows = store.get_core_insights(SMOKE_PIPELINE_URI).to_dict("records")
            _assert_equal(len(rows), 1)
            _assert_equal(rows[0]["Insight_ID"], "CI-1")
            _assert_equal(rows[0]["Spanning_Phases"], "Model Building")

        check("core-insights-phase-join", core_insights)
        check(
            "insight-code-order-and-text",
            lambda: _assert_equal(
                store.get_insight_code(SMOKE_INSIGHT_URI),
                [
                    {
                        "stmt_uri": f"{SMOKE_PIPELINE_URI}/s2",
                        "code_text": SMOKE_STATEMENT_TWO_TEXT,
                        "order": 2,
                    }
                ],
            ),
        )
    finally:
        if owned_store:
            store.close()

    failed = [item for item in checks if item["status"] == "failed"]
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "failed_check_count": len(failed),
        "fixture_build_id": SMOKE_BUILD_ID,
        "graph": values.get("SACK_TUGRAPH_GRAPH", "sack_poc"),
        "status": "passed" if not failed else "failed",
        "target": {"database": "TuGraph", "version": "4.5.2"},
    }
    report_path = output_root / "smoke_verification_report.json"
    report_path.write_text(
        json.dumps(report, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    if failed:
        raise TuGraphSmokeVerificationError(
            f"TuGraph smoke verification failed {len(failed)} checks; see {report_path}"
        )
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify P0 queries against the imported SACK TuGraph smoke fixture."
    )
    parser.add_argument("--result-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report = verify_tugraph_smoke_fixture(result_dir=args.result_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
