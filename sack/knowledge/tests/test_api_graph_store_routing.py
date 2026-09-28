import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional

import pandas as pd


class FakeGraphStore:
    def __init__(self):
        self.calls = []

    def get_top_pipelines(self, dataset_uri, k):
        self.calls.append(("pipelines", dataset_uri, k))
        return pd.DataFrame([{"Pipeline_id": "pipeline-uri"}])

    def get_core_insights(self, pipeline_uri):
        self.calls.append(("insights", pipeline_uri))
        return pd.DataFrame([{"Insight_ID": "i1"}])

    def get_competition_field(self, competition_uri, field):
        self.calls.append(("field", competition_uri, field))
        return "value"

    def get_insight_code(self, insight_uri):
        self.calls.append(("code", insight_uri))
        return [{"stmt_uri": "statement-uri", "code_text": "fit()", "order": 2}]

    def get_eda_insight(self, competition_uri, eda_type):
        self.calls.append(("eda", competition_uri, eda_type))
        return {"data_quality": {"missing": 0.1}}


def _load_api_module(monkeypatch):
    template = ModuleType("sack.knowledge.api.template")
    template.Any = Any
    template.Dict = Dict
    template.List = List
    template.Optional = Optional
    helper = ModuleType("sack.knowledge.api.helpers.helper")
    utils = ModuleType("sack.knowledge.api.utils")
    utils.profile_single_competition = lambda *args, **kwargs: None
    utils.get_current_competition_edainsight = lambda *args, **kwargs: None
    storage = ModuleType("sack.knowledge.storage_utils.get_current_comp_eda_files")
    storage.copy_eda_files = lambda *args, **kwargs: None
    tqdm_module = ModuleType("tqdm")
    tqdm_module.tqdm = lambda values, *args, **kwargs: values
    monkeypatch.setitem(sys.modules, "sack.knowledge.api.template", template)
    monkeypatch.setitem(sys.modules, "sack.knowledge.api.helpers.helper", helper)
    monkeypatch.setitem(sys.modules, "sack.knowledge.api.utils", utils)
    monkeypatch.setitem(
        sys.modules,
        "sack.knowledge.storage_utils.get_current_comp_eda_files",
        storage,
    )
    monkeypatch.setitem(sys.modules, "tqdm", tqdm_module)

    path = Path(__file__).parents[1] / "api" / "api.py"
    spec = importlib.util.spec_from_file_location("_sack_api_routing_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_facade_routes_migrated_agent_queries_without_changing_agent(monkeypatch):
    module = _load_api_module(monkeypatch)
    store = FakeGraphStore()
    facade = module.SACKKnowledgeBase.__new__(module.SACKKnowledgeBase)
    facade.graph_store = store
    facade.conn = object()

    dataset_uri = "http://sack.local/resource/kaggle/one"
    pipeline_uri = f"{dataset_uri}/pipeline"
    insight_uri = f"{pipeline_uri}/insight/i1"

    pipelines = facade.get_top_k_scoring_pipelines_for_dataset(dataset_uri, 3)
    insights = facade.get_core_insights_for_pipeline(pipeline_uri)
    field = facade.get_competition_field(dataset_uri, "overview")
    snippets = facade.get_insight_code_snippet(insight_uri)
    eda = facade.get_edainsight_for_competitions(dataset_uri, "pre_eda")

    assert pipelines.iloc[0]["Pipeline_id"] == "pipeline-uri"
    assert insights.iloc[0]["Insight_ID"] == "i1"
    assert field == "value"
    assert snippets == [{
        "stmt_uri": {"type": "uri", "value": "statement-uri"},
        "code_text": {"type": "literal", "value": "fit()"},
        "order": {
            "datatype": "http://www.w3.org/2001/XMLSchema#integer",
            "type": "literal",
            "value": "2",
        },
    }]
    assert eda == {"data_quality": {"missing": 0.1}}
    assert store.calls == [
        ("pipelines", dataset_uri, 3),
        ("insights", pipeline_uri),
        ("field", dataset_uri, "overview"),
        ("code", insight_uri),
        ("eda", dataset_uri, "pre_eda"),
    ]
