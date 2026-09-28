"""Build a small, deterministic TuGraph package for server smoke testing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sack.knowledge.graph.model import EdgeRecord, VertexRecord
from sack.knowledge.graph.schema_registry import SCHEMA_VERSION
from sack.knowledge.graph.sinks.tugraph import export_tugraph_package


SMOKE_BUILD_ID = "tugraph-4.5.2-smoke-v1"
SMOKE_SOURCE_URI = "http://sack.local/resource/smoke/source"
SMOKE_DATASET_URI = "http://sack.local/resource/smoke/competition-main"
SMOKE_OTHER_DATASET_URI = "http://sack.local/resource/smoke/competition-other"
SMOKE_TABLE_URI = f"{SMOKE_DATASET_URI}/train.csv"
SMOKE_COLUMN_URI = f"{SMOKE_TABLE_URI}/feature_a"
SMOKE_OTHER_COLUMN_URI = f"{SMOKE_TABLE_URI}/feature_b"
SMOKE_PIPELINE_URI = f"{SMOKE_DATASET_URI}/pipeline-1"
SMOKE_INSIGHT_URI = f"{SMOKE_PIPELINE_URI}/insight/CI-1"
SMOKE_OVERVIEW = "第一行\n第二行：中文与 emoji 🚀"
SMOKE_STATEMENT_TWO_TEXT = "model.fit(df[['feature_a']], y)"


def build_smoke_records(
    build_id: str = SMOKE_BUILD_ID,
) -> tuple[tuple[VertexRecord, ...], tuple[EdgeRecord, ...]]:
    """Return a representative graph that exercises every Agent P0 query shape."""

    def vertex(uri: str, label: str, **properties: Any) -> VertexRecord:
        return VertexRecord.from_uri(
            uri=uri,
            label=label,
            properties=properties,
            build_id=build_id,
        )

    source = vertex(SMOKE_SOURCE_URI, "Source", name="smoke-source")
    dataset = vertex(
        SMOKE_DATASET_URI,
        "Dataset",
        name="冒烟竞赛",
        overview=SMOKE_OVERVIEW,
        data_description="包含一个训练表。",
        problem_type="classification",
        data_type="tabular",
        domain="test",
        difficulty="easy",
    )
    other_dataset = vertex(
        SMOKE_OTHER_DATASET_URI,
        "Dataset",
        name="other-smoke-competition",
        overview="",
        data_description="candidate",
        problem_type="classification",
        data_type="tabular",
        domain="test",
        difficulty="easy",
    )
    table = vertex(
        SMOKE_TABLE_URI,
        "Table",
        name="train.csv",
        file_path="data/train.csv",
    )
    column = vertex(
        SMOKE_COLUMN_URI,
        "Column",
        name="feature_a",
        data_type="float64",
        total_count=10,
        distinct_count=8,
        missing_count=1,
        median=2.5,
        min_value=-1.0,
        max_value=9.0,
    )
    other_column = vertex(
        SMOKE_OTHER_COLUMN_URI,
        "Column",
        name="feature_b",
        data_type="float64",
        total_count=10,
        distinct_count=6,
        missing_count=0,
    )
    pre_eda_payload = {
        "eda_type": "pre_eda",
        "pre_eda_data_quality": {
            "missingness": {"overall_missing_rate": 0.1},
            "description": "缺失值\n1/10",
        },
        "pre_eda_basic_distribution": {
            "numerical": {"skewness_profile": {"highly_skewed_ratio": 0.2}}
        },
        "pre_eda_basic_dimensionality": {"samples_per_feature": 10.0},
    }
    deep_eda_payload = {
        "eda_type": "deep_eda",
        "deep_eda_feature_relationships": {
            "correlation_structure": {
                "correlation_strength": {"weak_correlation_ratio": 0.3}
            }
        },
        "deep_eda_complexity": {
            "noise_level": {"signal_to_noise_estimate": 2.0}
        },
        "deep_eda_special_scenarios": {
            "temporal_properties": {"is_time_series": False}
        },
    }
    pre_eda = vertex(
        f"{SMOKE_DATASET_URI}/pre-eda",
        "PreliminaryEDAInsight",
        payload_json=json.dumps(
            pre_eda_payload, ensure_ascii=False, separators=(",", ":")
        ),
    )
    deep_eda = vertex(
        f"{SMOKE_DATASET_URI}/deep-eda",
        "InDepthEDAInsight",
        payload_json=json.dumps(
            deep_eda_payload, ensure_ascii=False, separators=(",", ":")
        ),
    )
    pipeline = vertex(
        SMOKE_PIPELINE_URI,
        "Pipeline",
        title="smoke pipeline",
        author="migration-test",
        votes=7,
        written_on_raw="2026-09-22",
        source_url="https://example.invalid/smoke",
        score=0.875,
    )
    statement_one = vertex(
        f"{SMOKE_PIPELINE_URI}/s1",
        "Statement",
        text="df = pd.read_csv('train.csv')\n# 中文注释",
        phase="Data Preparation",
        ordinal=1,
        pipeline_uid=pipeline.uid,
    )
    statement_two = vertex(
        f"{SMOKE_PIPELINE_URI}/s2",
        "Statement",
        text=SMOKE_STATEMENT_TWO_TEXT,
        phase="Model Building",
        ordinal=2,
        pipeline_uid=pipeline.uid,
    )
    function = vertex(
        "http://sack.local/resource/smoke/library/pandas/read_csv",
        "Function",
        name="read_csv",
        qualified_name="pandas.read_csv",
    )
    parameter = vertex(
        f"{statement_one.uri}/parameter-filepath",
        "Parameter",
        name="filepath_or_buffer",
    )
    tag = vertex(
        "http://sack.local/resource/smoke/tag/tabular",
        "Tag",
        name="Tabular",
        normalized_name="tabular",
    )
    insight = vertex(
        SMOKE_INSIGHT_URI,
        "CoreInsight",
        name="smoke insight",
        insight_id="CI-1",
        description="读取后训练；保留多行代码。",
        insight_type="workflow",
        effectiveness="high",
        evidence="smoke fixture",
        phase="Model Building",
    )
    phase = vertex(
        "http://sack.local/resource/phase/Model+Building",
        "Phase",
        name="Model Building",
        sort_order=2,
    )
    vertices = (
        source,
        dataset,
        other_dataset,
        table,
        column,
        other_column,
        pre_eda,
        deep_eda,
        pipeline,
        statement_one,
        statement_two,
        function,
        parameter,
        tag,
        insight,
        phase,
    )

    def edge(
        edge_type: str,
        source_vertex: VertexRecord,
        target_vertex: VertexRecord,
        *,
        scope: VertexRecord | None = None,
        discriminator: Any = None,
        **properties: Any,
    ) -> EdgeRecord:
        return EdgeRecord.from_endpoints(
            edge_type=edge_type,
            src_uid=source_vertex.uid,
            dst_uid=target_vertex.uid,
            properties=properties,
            build_id=build_id,
            scope_uid=scope.uid if scope is not None else None,
            discriminator=discriminator,
        )

    edges = (
        edge("IS_PART_OF", dataset, source),
        edge("IS_PART_OF", other_dataset, source),
        edge("IS_PART_OF", table, dataset),
        edge("IS_PART_OF", column, table),
        edge("IS_PART_OF", other_column, table),
        edge("HAS_CONTENT_SIMILARITY", column, other_column, certainty=0.875),
        edge("HAS_CONTENT_SIMILARITY", other_column, column, certainty=0.875),
        edge("HAS_LABEL_SIMILARITY", column, other_column, certainty=0.625),
        edge("HAS_LABEL_SIMILARITY", other_column, column, certainty=0.625),
        edge("IS_PART_OF", pipeline, dataset),
        edge("IS_PART_OF", statement_one, pipeline),
        edge("IS_PART_OF", statement_two, pipeline),
        edge("HAS_PRELIMINARY_EDA_INSIGHT", dataset, pre_eda),
        edge("HAS_IN_DEPTH_EDA_INSIGHT", dataset, deep_eda),
        edge("NEXT_STATEMENT", statement_one, statement_two, scope=pipeline),
        edge("DATA_FLOW_TO", statement_one, statement_two, scope=pipeline),
        edge("CALLS_FUNCTION", statement_one, function, scope=pipeline),
        edge("READS_TABLE", statement_one, table, scope=pipeline),
        edge("READS_COLUMN", statement_one, column, scope=pipeline),
        edge(
            "HAS_PARAMETER",
            statement_one,
            parameter,
            scope=pipeline,
            discriminator="filepath_or_buffer",
            value="train.csv",
            value_type="str",
        ),
        edge("HAS_TAG", pipeline, tag),
        edge("HAS_CORE_INSIGHT", pipeline, insight, scope=pipeline),
        edge("IMPLEMENTED_IN", insight, statement_two, scope=pipeline),
        edge("SPANS_PHASE", insight, phase),
    )
    return vertices, edges


def build_tugraph_smoke_fixture(
    output_dir: str | Path,
    *,
    build_id: str = SMOKE_BUILD_ID,
):
    vertices, edges = build_smoke_records(build_id)
    return export_tugraph_package(
        vertices,
        edges,
        output_dir,
        source_schema_version=SCHEMA_VERSION,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the deterministic SACK TuGraph server smoke package."
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--build-id", default=SMOKE_BUILD_ID)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    manifest = build_tugraph_smoke_fixture(
        args.output_dir,
        build_id=args.build_id,
    )
    print(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
