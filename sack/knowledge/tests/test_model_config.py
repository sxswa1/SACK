"""Verify effective model selection and request routing without model calls."""

import ast
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from sack.model_config import DEFAULT_MODELS, FALLBACK_ROLES, get_model, infer_endpoint_role


ROOT = Path(__file__).parents[3]


@pytest.fixture(autouse=True)
def clean_model_environment(monkeypatch):
    for role in DEFAULT_MODELS.keys() | FALLBACK_ROLES.keys():
        monkeypatch.delenv(f"SACK_MODEL_{role.upper()}", raising=False)


def load_definitions(relative, names, **extra):
    """Execute real class/functions while isolating heavyweight dependencies."""
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8-sig"))
    definitions = [node for node in tree.body
                   if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names]
    assert len(definitions) == len(names)
    future = ast.parse("from __future__ import annotations").body
    namespace = {
        "get_model": get_model,
        "infer_endpoint_role": infer_endpoint_role,
        "logger": logging.getLogger(__name__),
        "logging": logging,
        **extra,
    }
    exec(compile(ast.fix_missing_locations(ast.Module(body=future + definitions, type_ignores=[])),
                 relative, "exec"), namespace)
    return namespace


@pytest.mark.parametrize("role,parent", list(FALLBACK_ROLES.items()))
def test_role_override_falls_back_to_family_and_respects_explicit_value(monkeypatch, role, parent):
    monkeypatch.setenv(f"SACK_MODEL_{parent.upper()}", "family-model")
    assert get_model(role) == "family-model"
    monkeypatch.setenv(f"SACK_MODEL_{role.upper()}", "  role-model  ")
    assert get_model(role) == "role-model"


def test_empty_and_unknown_model_settings_are_rejected(monkeypatch):
    monkeypatch.setenv("SACK_MODEL_CODER", "  ")
    with pytest.raises(ValueError, match="SACK_MODEL_CODER"):
        get_model("developer")
    with pytest.raises(ValueError, match="Unknown model role"):
        get_model("typo")


@pytest.mark.parametrize("agent,role", [
    ("Reader", "reader"), ("Planner", "planner"), ("EDAPlanner", "planner"),
    ("Developer", "developer"), ("EDADeveloper", "developer"),
    ("Reviewer", "reviewer"), ("EDAReviewer", "reviewer"),
    ("Summarizer", "summarizer"), ("EDASummarizer", "summarizer"),
])
def test_sop_constructs_each_agent_with_its_configured_model(monkeypatch, agent, role):
    monkeypatch.setenv(f"SACK_MODEL_{role.upper()}", "selected-agent-model")
    constructors = {name: lambda model, kind: (model, kind)
                    for name in ["Reader", "Planner", "EDAPlanner", "Developer", "EDADeveloper",
                                 "Reviewer", "EDAReviewer", "Summarizer", "EDASummarizer"]}
    namespace = load_definitions("sack/sop.py", ["SOP"], **constructors)
    sop = object.__new__(namespace["SOP"])
    assert sop._create_agent(agent) == ("selected-agent-model", "api")


def api_namespace():
    calls = []

    class APIError(Exception):
        pass

    class BadRequestError(APIError):
        pass

    class NotFoundError(APIError):
        pass

    def create(**kwargs):
        calls.append(("request", kwargs))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))])

    def client(**kwargs):
        calls.append(("client", kwargs))
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    openai = SimpleNamespace(OpenAI=client, APIError=APIError, BadRequestError=BadRequestError,
                             NotFoundError=NotFoundError, APIConnectionError=APIError,
                             RateLimitError=APIError)
    namespace = load_definitions(
        "sack/api_handler.py", ["APIHandler", "generate_response"],
        openai=openai, httpx=SimpleNamespace(Client=lambda **kwargs: object()),
        load_api_config=lambda: ("test-key", "https://general.invalid/v1",
                                 "https://coder.invalid/v1", "https://vision.invalid/v1"),
        time=SimpleNamespace(time=lambda: 0, sleep=lambda seconds: calls.append(("sleep", seconds))),
        MAX_ATTEMPTS=2, RETRY_DELAY=0,
    )
    return namespace, calls, openai


@pytest.mark.parametrize("role", ["general", "coder", "vision"])
def test_same_model_name_can_use_each_roles_distinct_endpoint(monkeypatch, role):
    for family in ("general", "coder", "vision"):
        monkeypatch.setenv(f"SACK_MODEL_{family.upper()}", "shared-model")
    namespace, calls, _ = api_namespace()
    handler = namespace["APIHandler"]("shared-model", endpoint_role=role)
    settings = SimpleNamespace(temperature=0, max_completion_tokens=16, top_p=1,
                               frequency_penalty=0, presence_penalty=0, stop=None, timeout=5)
    assert handler.get_output([{"role": "user", "content": "hello"}], settings) == "OK"
    assert calls[0][1]["base_url"] == f"https://{role}.invalid/v1"
    assert calls[1][1]["model"] == "shared-model"


@pytest.mark.parametrize("role,endpoint", [("coder", "coder"), ("debug", "coder"), ("vision", "vision")])
def test_model_only_client_routes_configured_names(monkeypatch, role, endpoint):
    monkeypatch.setenv(f"SACK_MODEL_{role.upper()}", "arbitrary-model-id")
    namespace, _, _ = api_namespace()
    handler = namespace["APIHandler"](get_model(role))
    assert handler.base_url == f"https://{endpoint}.invalid/v1"


def test_model_not_found_is_preserved_without_retries():
    namespace, calls, openai = api_namespace()
    error = openai.NotFoundError("model_not_found")

    def fail(*args):
        calls.append(("failed-request", None))
        raise error

    namespace["generate_response"] = fail
    handler = namespace["APIHandler"]("missing-model")
    with pytest.raises(openai.NotFoundError) as caught:
        handler.get_output([], object())
    assert caught.value is error
    assert [kind for kind, _ in calls].count("failed-request") == 1
    assert not any(kind == "sleep" for kind, _ in calls)


def test_retry_exhaustion_raises_original_error_not_unbound_local():
    namespace, calls, openai = api_namespace()
    error = openai.APIError("temporary failure")

    def fail(*args):
        calls.append(("failed-request", None))
        raise error

    namespace["generate_response"] = fail
    handler = namespace["APIHandler"]("temporary-model")
    with pytest.raises(openai.APIError) as caught:
        handler.get_output([], object())
    assert caught.value is error
    assert [kind for kind, _ in calls].count("failed-request") == 2


@pytest.mark.parametrize("relative,role", [("sack/Tools/debug.py", "debug"),
                                         ("sack/Tools/unit_test.py", "test")])
def test_debug_and_test_tools_use_role_models_and_coder_endpoint(monkeypatch, relative, role):
    monkeypatch.setenv(f"SACK_MODEL_{role.upper()}", "tool-model")
    calls = []
    name = "DebugTool" if role == "debug" else "TestTool"
    namespace = load_definitions(relative, [name],
                                 LLM=lambda *args, **kwargs: calls.append((args, kwargs)),
                                 pd=SimpleNamespace(set_option=lambda *args: None))
    namespace[name]()
    namespace[name](model="explicit-model")
    assert calls == [(("tool-model", "api"), {"endpoint_role": "coder"}),
                     (("explicit-model", "api"), {"endpoint_role": "coder"})]


def test_image_tool_passes_selected_model_to_actual_image_reader(monkeypatch):
    monkeypatch.setenv("SACK_MODEL_VISION", "selected-vision-model")
    calls = []

    def read_image(prompt, path, model=None):
        calls.append((path, model))
        return "image description"

    namespace = load_definitions("sack/Tools/image_to_text.py", ["ImageToTextTool"],
                                 LLM=lambda *args, **kwargs: None, read_image=read_image)
    tool = namespace["ImageToTextTool"]()
    state = SimpleNamespace(restore_dir="/example")
    assert tool.image_to_text(state, ["plot.png"]) == {"plot.png": "image description"}
    assert calls == [("/example/images/plot.png", "selected-vision-model")]


@pytest.mark.parametrize("role,endpoint", [("developer", "coder"), ("planner", "general")])
def test_agent_keeps_role_endpoint_when_model_names_overlap(monkeypatch, role, endpoint):
    calls = []
    fake_module = SimpleNamespace(LLM=lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setitem(sys.modules, "sack.LLMComponent.llm", fake_module)
    namespace = load_definitions("sack/Agents/agent_base.py", ["Agent"])
    namespace["Agent"](role, "description", "shared-model", "api")
    assert calls == [(("shared-model", "api"), {"endpoint_role": endpoint})]


@pytest.mark.parametrize("relative,role,dimensions", [
    ("sack/LLMComponent/llm.py", "embedding", 1024),
    ("sack/knowledge/LLMUsage/llm.py", "knowledge_embedding", None),
])
def test_embedding_model_selection_preserves_each_clients_vector_contract(monkeypatch, relative, role, dimensions):
    monkeypatch.setenv(f"SACK_MODEL_{role.upper()}", "selected-embedding-model")
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(data=["vector"])

    namespace = load_definitions(relative, ["OpenaiEmbeddings"],
                                 OpenAI=lambda **kwargs: SimpleNamespace(embeddings=SimpleNamespace(create=create)),
                                 httpx=SimpleNamespace(Client=lambda **kwargs: object()))
    embedding = namespace["OpenaiEmbeddings"]("test-key")
    assert embedding.encode("example") == ["vector"]
    assert calls[0]["model"] == "selected-embedding-model"
    assert calls[0].get("dimensions") == dimensions
    explicit = namespace["OpenaiEmbeddings"]("test-key", model="explicit-embedding")
    assert explicit.model == "explicit-embedding"
