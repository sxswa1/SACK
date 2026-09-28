"""Small parameterized Bolt client for TuGraph 4.5.2.

The Neo4j driver import is intentionally lazy.  CIR construction and package
generation therefore remain usable without installing an online database
client.  Business code depends on ``run`` rather than on Neo4j result objects.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any


class TuGraphClientError(RuntimeError):
    """Raised when the Bolt driver cannot be created or a query fails."""


class TuGraphBoltClient:
    def __init__(
        self,
        *,
        uri: str,
        graph: str,
        user: str,
        password: str,
        connection_timeout_seconds: float = 10.0,
        driver_factory: Callable[..., Any] | None = None,
    ) -> None:
        if not uri.startswith(("bolt://", "neo4j://")):
            raise ValueError("TuGraph Bolt URI must start with bolt:// or neo4j://")
        if not graph or not user:
            raise ValueError("TuGraph graph and user must be non-empty")
        if not isinstance(password, str) or not password:
            raise ValueError("TuGraph password must be a non-empty string")
        if connection_timeout_seconds <= 0:
            raise ValueError("connection_timeout_seconds must be positive")

        if driver_factory is None:
            try:
                from neo4j import GraphDatabase
            except ModuleNotFoundError as exc:
                raise TuGraphClientError(
                    "Neo4j Python driver is required for TuGraph Bolt access; "
                    "install the migration environment dependencies"
                ) from exc
            driver_factory = GraphDatabase.driver
        try:
            self._driver = driver_factory(
                uri,
                auth=(user, password),
                connection_timeout=connection_timeout_seconds,
            )
        except Exception as exc:
            raise TuGraphClientError(f"Cannot create TuGraph Bolt driver: {exc}") from exc
        self._graph = graph

    def run(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> list[Mapping[str, Any]]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Cypher query must be a non-empty string")
        values = dict(parameters or {})
        try:
            with self._driver.session(database=self._graph) as session:
                result = session.run(query, values)
                rows: Sequence[Mapping[str, Any]] = result.data()
        except Exception as exc:
            raise TuGraphClientError(f"TuGraph Cypher query failed: {exc}") from exc
        return [dict(row) for row in rows]

    def close(self) -> None:
        try:
            self._driver.close()
        except Exception as exc:
            raise TuGraphClientError(f"Cannot close TuGraph Bolt driver: {exc}") from exc

    def __enter__(self) -> "TuGraphBoltClient":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
