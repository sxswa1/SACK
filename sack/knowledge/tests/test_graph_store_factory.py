import pytest

from sack.knowledge.stores.factory import (
    GraphStoreConfigurationError,
    create_agent_graph_store,
)
from sack.knowledge.stores.tugraph import TuGraphGraphStore


class FakeClient:
    def run(self, query, parameters=None):
        return []

    def close(self):
        return None


def test_factory_keeps_graphdb_as_safe_default():
    assert create_agent_graph_store(environ={}) is None


def test_factory_builds_tugraph_store_from_environment_without_leaking_password():
    calls = []

    def factory(**kwargs):
        calls.append(kwargs)
        return FakeClient()

    store = create_agent_graph_store(
        environ={
            "SACK_AGENT_GRAPH_BACKEND": "tugraph",
            "SACK_TUGRAPH_BOLT_URL": "bolt://server:7687",
            "SACK_TUGRAPH_GRAPH": "sack_v1",
            "SACK_TUGRAPH_USER": "reader",
            "SACK_TUGRAPH_PASSWORD": "secret",
        },
        client_factory=factory,
    )

    assert isinstance(store, TuGraphGraphStore)
    assert calls == [{
        "uri": "bolt://server:7687",
        "graph": "sack_v1",
        "user": "reader",
        "password": "secret",
    }]


def test_factory_requires_password_for_tugraph():
    with pytest.raises(GraphStoreConfigurationError, match="PASSWORD") as exc_info:
        create_agent_graph_store(
            environ={"SACK_AGENT_GRAPH_BACKEND": "tugraph"},
            client_factory=lambda **kwargs: FakeClient(),
        )

    assert "secret" not in str(exc_info.value)


def test_factory_rejects_unknown_backend():
    with pytest.raises(GraphStoreConfigurationError, match="graphdb or tugraph"):
        create_agent_graph_store(environ={"SACK_AGENT_GRAPH_BACKEND": "auto"})


def test_factory_accepts_documented_general_backend_variable():
    store = create_agent_graph_store(
        environ={
            "SACK_GRAPH_BACKEND": "tugraph",
            "SACK_TUGRAPH_PASSWORD": "secret",
        },
        client_factory=lambda **kwargs: FakeClient(),
    )

    assert isinstance(store, TuGraphGraphStore)
