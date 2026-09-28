"""Storage-neutral contracts used by the SACK knowledge facade."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

import pandas as pd


class CypherClient(Protocol):
    def run(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> list[Mapping[str, Any]]: ...

    def close(self) -> None: ...


class GraphStore(Protocol):
    """P0 domain operations; arbitrary query-language execution is excluded."""

    def healthcheck(self) -> bool: ...

    def get_top_pipelines(
        self,
        dataset_uri: str | None,
        k: int | None,
    ) -> pd.DataFrame: ...

    def find_candidate_competitions(
        self,
        problem_type: str,
        data_type: str,
        exclude_uri: str,
    ) -> list[str]: ...

    def list_competitions(self) -> list[dict[str, Any]]: ...

    def get_competition_name(self, competition_uri: str) -> str | None: ...

    def get_competition_tables(self, competition_uri: str) -> list[dict[str, Any]]: ...

    def get_eda_insight(
        self,
        competition_uri: str,
        eda_type: str,
    ) -> dict[str, Any]: ...

    def get_core_insights(self, pipeline_uri: str) -> pd.DataFrame: ...

    def get_competition_field(self, competition_uri: str, field: str) -> str | None: ...

    def get_insight_code(self, insight_uri: str) -> list[dict[str, Any]]: ...

    def close(self) -> None: ...
