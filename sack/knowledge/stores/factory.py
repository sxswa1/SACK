"""Configuration boundary for selecting the Agent's graph read backend."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any

from sack.knowledge.clients.tugraph_bolt import TuGraphBoltClient
from sack.knowledge.stores.base import GraphStore
from sack.knowledge.stores.tugraph import TuGraphGraphStore


class GraphStoreConfigurationError(ValueError):
    """Raised when backend configuration is missing or unsupported."""


def create_agent_graph_store(
    *,
    backend: str | None = None,
    environ: Mapping[str, str] | None = None,
    client_factory: Callable[..., Any] = TuGraphBoltClient,
) -> GraphStore | None:
    """Create the optional migrated P0 store.

    ``None`` means that the existing GraphDB methods remain authoritative.
    TuGraph credentials are read only from the supplied environment and are
    never included in error messages or object representations.
    """

    values = os.environ if environ is None else environ
    selected = (
        backend
        or values.get("SACK_AGENT_GRAPH_BACKEND")
        or values.get("SACK_GRAPH_BACKEND")
        or "graphdb"
    ).strip().lower()
    if selected == "graphdb":
        return None
    if selected != "tugraph":
        raise GraphStoreConfigurationError(
            "Graph backend must be graphdb or tugraph"
        )

    password = values.get("SACK_TUGRAPH_PASSWORD")
    if not password:
        raise GraphStoreConfigurationError(
            "SACK_TUGRAPH_PASSWORD is required when the Agent graph backend is TuGraph"
        )
    client = client_factory(
        uri=values.get("SACK_TUGRAPH_BOLT_URL", "bolt://127.0.0.1:7687"),
        graph=values.get("SACK_TUGRAPH_GRAPH", "sack_poc"),
        user=values.get("SACK_TUGRAPH_USER", "admin"),
        password=password,
    )
    return TuGraphGraphStore(client)
