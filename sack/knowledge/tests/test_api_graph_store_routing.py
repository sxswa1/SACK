import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional

import pandas as pd
import pytest


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
    utils.profile_input_manifest = lambda *args, **kwargs: {}
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


def test_graphdb_public_eda_preserves_core_dictionary(monkeypatch):
    module = _load_api_module(monkeypatch)
    facade = module.SACKKnowledgeBase.__new__(module.SACKKnowledgeBase)
    facade.graph_store = None
    facade.conn = object()
    expected = {'data_quality': {'missing': 0.1}}
    monkeypatch.setattr(module, 'get_edainsight_for_competitions_core', lambda **kwargs: expected, raising=False)
    assert facade.get_edainsight_for_competitions('http://sack.local/resource/kaggle/titanic', 'pre_eda') == expected
    monkeypatch.setattr(module, 'get_edainsight_for_competitions_core', lambda **kwargs: {}, raising=False)
    assert facade.get_edainsight_for_competitions('http://sack.local/resource/kaggle/titanic', 'pre_eda') == {}


def test_profile_missing_columns_and_nonfinite_vectors_rejected(monkeypatch):
    module = _load_api_module(monkeypatch)
    facade = module.SACKKnowledgeBase.__new__(module.SACKKnowledgeBase)
    current = {'comp_id': 'kaggle/titanic', 'overview_embedding': [], 'data_description_embedding': [],
               'profile_schema_version': 2, 'tables': [{'table_name': 'train.csv',
               'expected_columns': ['Age', 'Fare'], 'columns': [{'col_name': 'Age',
               'label_embedding': [0.0] * 300, 'content_embedding': [0.0] * 300}]}]}
    with pytest.raises(ValueError, match='coverage incomplete'):
        facade._validate_current_comp(current)
    current['tables'][0]['expected_columns'] = ['Age']
    current['tables'][0]['columns'][0]['content_embedding'][0] = float('nan')
    with pytest.raises(ValueError, match='Invalid content_embedding'):
        facade._validate_current_comp(current)


def test_profile_reads_explicit_source_and_rejects_stale_cache(monkeypatch, tmp_path):
    module = _load_api_module(monkeypatch)
    facade = module.SACKKnowledgeBase.__new__(module.SACKKnowledgeBase)
    source = tmp_path / 'current_dsp'
    source.mkdir()
    cached = {'comp_id': 'kaggle/titanic', 'overview_embedding': [0.0] * 300,
              'data_description_embedding': [0.0] * 300, 'tables': [{'table_name': 'train.csv',
              'columns': [{'col_name': 'Age', 'label_embedding': [0.0] * 300,
              'content_embedding': [0.0] * 300}]}], 'input_manifest': {'train.csv': 'old'}}
    import json
    (tmp_path / 'titanic_profile.json').write_text(json.dumps(cached))
    calls = []
    monkeypatch.setattr(module, 'profile_input_manifest', lambda path: {'train.csv': 'new'})
    def profile(new_comp_path):
        calls.append(new_comp_path)
        return {'comp_id': 'kaggle/titanic', 'overview': '', 'data_description': '',
                'overview_embedding': [0.0] * 300, 'data_description_embedding': [0.0] * 300,
                'structured_elements': {'problem_type': 'binary_classification', 'data_type': 'tabular'}}, cached['tables']
    monkeypatch.setattr(module, 'profile_single_competition', profile)
    result = facade.generate_competition_profile('titanic', persist_path=str(tmp_path), source_path=str(source))
    assert calls == [str(source)]
    assert result['input_manifest'] == {'train.csv': 'new'}
    assert facade.generate_competition_profile('titanic', persist_path=str(tmp_path), source_path=str(source)) == result
    assert len(calls) == 1


def test_postgres_deployment_environment_preserves_explicit_overrides(monkeypatch, tmp_path):
    module = _load_api_module(monkeypatch)
    calls = []
    monkeypatch.setattr(module, "connect_to_graphdb", lambda *args, **kwargs: object(), raising=False)
    monkeypatch.setattr(module, "connect_to_postgres", lambda **kwargs: calls.append(kwargs) or object(), raising=False)
    monkeypatch.setattr(module, "create_agent_graph_store", lambda **kwargs: None)
    password_file = tmp_path / "password"
    password_file.write_text("test-file-password\n")
    monkeypatch.setenv("SACK_PG_HOST", "127.0.0.1")
    monkeypatch.setenv("SACK_PG_USER", "sack_knowledge_reader")
    monkeypatch.setenv("SACK_PG_PORT", "5433")
    monkeypatch.setenv("SACK_PG_PASSWORD_FILE", str(password_file))
    monkeypatch.delenv("SACK_PG_PASSWORD", raising=False)
    module.SACKKnowledgeBase()
    assert calls[0]["user"] == "sack_knowledge_reader"
    assert calls[0]["password"] == "test-file-password"
    assert calls[0]["host"] == "127.0.0.1"
    assert calls[0]["port"] == "5433"
    calls.clear()
    module.SACKKnowledgeBase(pg_host="explicit-host", pg_user="explicit-user",
                             pg_password="explicit-password", pg_port="5434")
    assert calls[0]["user"] == "explicit-user"
    assert calls[0]["password"] == "explicit-password"
    assert calls[0]["host"] == "explicit-host"
    assert calls[0]["port"] == "5434"
    calls.clear()
    monkeypatch.setenv("SACK_PG_PASSWORD", "test-environment-password")
    module.SACKKnowledgeBase()
    assert calls[0]["password"] == "test-environment-password"


def test_postgres_unconfigured_deployment_keeps_legacy_defaults(monkeypatch):
    module = _load_api_module(monkeypatch)
    calls = []
    monkeypatch.setattr(module, "connect_to_graphdb", lambda *args, **kwargs: object(), raising=False)
    monkeypatch.setattr(module, "connect_to_postgres", lambda **kwargs: calls.append(kwargs) or object(), raising=False)
    monkeypatch.setattr(module, "create_agent_graph_store", lambda **kwargs: None)
    for name in ("HOST", "USER", "PORT", "PASSWORD", "PASSWORD_FILE"):
        monkeypatch.delenv("SACK_PG_" + name, raising=False)
    module.SACKKnowledgeBase()
    assert calls[0]["host"] == "localhost"
    assert calls[0]["user"] == "postgres"
    assert calls[0]["password"] == "postgres"
    assert calls[0]["port"] == module.SACKKnowledgeConfig.postgresql_port
