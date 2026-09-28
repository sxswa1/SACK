import pytest

from sack.knowledge.graph.builders.pipeline import (
    PipelineBuildError,
    build_pipeline_records,
    build_pipeline_records_from_metadata,
)
from sack.knowledge.graph.validation import validate_graph


BUILD_ID = "pipeline-test"
PIPELINE_URI = "http://sack.local/resource/kaggle/titanic/pipeline-1"


def fixture_input():
    pipeline_info = {
        "uri": PIPELINE_URI,
        "dataset": "http://sack.local/resource/kaggle/titanic",
        "title": "Titanic baseline",
        "author": "analyst",
        "votes": 7,
        "date": "2025-01-02 03:04:05",
        "tags": ["Getting Started", "Classification"],
        "url": "https://example.test/pipeline-1",
        "score": 0.81,
    }
    nodes = [
        {
            "uri": f"{PIPELINE_URI}/s1",
            "next": f"{PIPELINE_URI}/s2",
            "text": "df = pd.read_csv('train.csv')",
            "control_flow": ["http://sack.local/resource/import"],
            "parameters": [
                {"parameter": "filepath_or_buffer", "parameter_value": "train.csv"}
            ],
            "calls": [
                {
                    "uri": "http://sack.local/resource/library/pandas/read_csv",
                    "call_type": "callsFunction",
                }
            ],
            "read": [
                {
                    "uri": "http://sack.local/resource/kaggle/titanic/train.csv",
                    "type": "readsTable",
                }
            ],
            "dataFlow": [f"{PIPELINE_URI}/s2"],
            "phase": "Data Loading",
        },
        {
            "uri": f"{PIPELINE_URI}/s2",
            "next": None,
            "text": "model.fit(df)",
            "control_flow": [],
            "parameters": [],
            "calls": [],
            "read": [
                {
                    "uri": "http://sack.local/resource/kaggle/titanic/train.csv/Age",
                    "type": "readsColumn",
                }
            ],
            "dataFlow": [],
            "phase": "Model Training",
        },
    ]
    file_elements = [
        {
            "uri": "http://sack.local/resource/kaggle/titanic/train.csv",
            "contain": [
                {"uri": "http://sack.local/resource/kaggle/titanic/train.csv/Age"}
            ],
        }
    ]
    libraries = {
        "pandas": {
            "uri": "http://sack.local/resource/library/pandas",
            "type": "http://sack.local/ontology/Library",
            "contain": [
                {
                    "uri": "http://sack.local/resource/library/pandas/read_csv",
                    "type": "http://sack.local/ontology/Function",
                    "contain": [],
                }
            ],
        }
    }
    core_insights = {
        "phase_insights": {
            "Model Training": [
                {
                    "insight_id": "fit-model",
                    "type": "DS",
                    "description": "Fit a baseline model.",
                    "effectiveness_reasoning": "Establishes a baseline.",
                    "significance": "High",
                    "transferability": "High",
                    "evidence": "Validation improved.",
                    "implementing_node_ids": ["s2"],
                }
            ]
        },
        "cross_phase_insights": [
            {
                "insight_id": "consistent-data-flow",
                "type": "ARCH",
                "description": "Keep data flow consistent.",
                "effectiveness_reasoning": "Avoids train/serve skew.",
                "significance": "Medium",
                "transferability": "High",
                "evidence": "Same frame is reused.",
                "implementing_node_ids": ["s1", "s2"],
                "spanning_phases": ["Data Loading", "Model Training"],
            }
        ],
    }
    return pipeline_info, nodes, file_elements, libraries, core_insights


def records_by_label(records, label):
    return [record for record in records if record.label == label]


def edges_by_type(records, edge_type):
    return [record for record in records if record.edge_type == edge_type]


def test_pipeline_conversion_preserves_scope_rdf_star_and_core_insights():
    pipeline_info, nodes, files, libraries, insights = fixture_input()

    result = build_pipeline_records(
        pipeline_info=pipeline_info,
        nodes=nodes,
        file_elements=files,
        libraries=libraries,
        core_insights=insights,
        build_id=BUILD_ID,
    )

    assert len(records_by_label(result.vertices, "Pipeline")) == 1
    assert len(records_by_label(result.vertices, "Statement")) == 2
    assert len(records_by_label(result.vertices, "CoreInsight")) == 2
    assert len(records_by_label(result.vertices, "Tag")) == 2
    assert len(edges_by_type(result.edges, "NEXT_STATEMENT")) == 1
    assert len(edges_by_type(result.edges, "DATA_FLOW_TO")) == 1
    assert len(edges_by_type(result.edges, "IMPLEMENTED_IN")) == 3
    assert len(edges_by_type(result.edges, "SPANS_PHASE")) == 2
    assert {phase.properties["name"] for phase in records_by_label(result.vertices, "Phase")} == {
        "Data Loading",
        "Model Training",
    }

    binding = edges_by_type(result.edges, "HAS_PARAMETER")[0]
    assert binding.properties == {"value": "train.csv", "value_type": "string"}
    pipeline_uid = records_by_label(result.vertices, "Pipeline")[0].uid
    scoped_types = {
        "NEXT_STATEMENT",
        "DATA_FLOW_TO",
        "CALLS_FUNCTION",
        "READS_TABLE",
        "READS_COLUMN",
        "HAS_PARAMETER",
        "HAS_CORE_INSIGHT",
        "IMPLEMENTED_IN",
    }
    assert all(
        edge.scope_uid == pipeline_uid
        for edge in result.edges
        if edge.edge_type in scoped_types
    )
    report = validate_graph(result.vertices, result.edges)
    assert report.is_valid, report.errors


def test_pipeline_conversion_rejects_dangling_statement_flow():
    pipeline_info, nodes, files, libraries, insights = fixture_input()
    nodes[0]["next"] = f"{PIPELINE_URI}/s99"

    with pytest.raises(PipelineBuildError, match="missing Statement"):
        build_pipeline_records(
            pipeline_info=pipeline_info,
            nodes=nodes,
            file_elements=files,
            libraries=libraries,
            core_insights=insights,
            build_id=BUILD_ID,
        )


def test_pipeline_conversion_rejects_unknown_call_type():
    pipeline_info, nodes, files, libraries, insights = fixture_input()
    nodes[0]["calls"][0]["call_type"] = "callsMystery"

    with pytest.raises(PipelineBuildError, match="Unsupported statement call type"):
        build_pipeline_records(
            pipeline_info=pipeline_info,
            nodes=nodes,
            file_elements=files,
            libraries=libraries,
            core_insights=insights,
            build_id=BUILD_ID,
        )


def test_pipeline_conversion_rejects_conflicting_parameter_binding():
    pipeline_info, nodes, files, libraries, insights = fixture_input()
    nodes[0]["parameters"].append(
        {"parameter": "filepath_or_buffer", "parameter_value": "other.csv"}
    )

    with pytest.raises(PipelineBuildError, match="Conflicting edge records"):
        build_pipeline_records(
            pipeline_info=pipeline_info,
            nodes=nodes,
            file_elements=files,
            libraries=libraries,
            core_insights=insights,
            build_id=BUILD_ID,
        )


def test_version_two_metadata_can_be_replayed_losslessly():
    pipeline_info, nodes, files, libraries, insights = fixture_input()
    metadata = {
        "metadata_version": 2,
        "pipeline_id": "pipeline-1",
        "dataset_name": "titanic",
        "pipeline_info": pipeline_info,
        "libraries": libraries,
        "nodes": nodes,
        "file_elements": files,
        "nodes_count": len(nodes),
        "file_elements_count": len(files),
    }

    replayed = build_pipeline_records_from_metadata(
        metadata,
        build_id=BUILD_ID,
        complete_analysis={"core_insights": insights},
    )
    direct = build_pipeline_records(
        pipeline_info=pipeline_info,
        nodes=nodes,
        file_elements=files,
        libraries=libraries,
        core_insights=insights,
        build_id=BUILD_ID,
    )

    assert replayed == direct


def test_legacy_count_only_metadata_is_rejected():
    pipeline_info, nodes, files, libraries, _ = fixture_input()
    legacy = {
        "pipeline_info": pipeline_info,
        "libraries": libraries,
        "nodes_count": len(nodes),
        "file_elements_count": len(files),
    }

    with pytest.raises(PipelineBuildError, match="predates lossless version 2"):
        build_pipeline_records_from_metadata(legacy, build_id=BUILD_ID)
