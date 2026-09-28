"""P0 SACK domain queries implemented with parameterized TuGraph Cypher."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from sack.knowledge.api.edainsight_similarity import FIELD_WEIGHTS
from sack.knowledge.graph.id_codec import vertex_uid
from sack.knowledge.stores.base import CypherClient


class TuGraphStoreError(RuntimeError):
    """Raised when TuGraph returns a row that violates the domain contract."""


_PIPELINE_COLUMNS = [
    "Pipeline_id",
    "Pipeline",
    "Author",
    "Written_on",
    "Number_of_votes",
    "Score",
]
_INSIGHT_COLUMNS = [
    "Insight_ID",
    "Description",
    "Insight_Type",
    "Effectiveness",
    "Evidence",
    "Phase",
    "Spanning_Phases",
]
_COMPETITION_FIELDS = frozenset(
    {
        "overview",
        "data_description",
        "problem_type",
        "data_type",
        "domain",
        "difficulty",
    }
)
_SIMILARITY_RELATIONS = frozenset(
    {"HAS_CONTENT_SIMILARITY", "HAS_LABEL_SIMILARITY"}
)


class TuGraphGraphStore:
    """TuGraph query implementation kept independent of the Agent layer."""

    def __init__(self, client: CypherClient) -> None:
        self._client = client

    def healthcheck(self) -> bool:
        rows = self._client.run("RETURN 1 AS ok", {})
        return len(rows) == 1 and rows[0].get("ok") == 1

    def get_top_pipelines(
        self,
        dataset_uri: str | None,
        k: int | None,
    ) -> pd.DataFrame:
        if dataset_uri is not None and not isinstance(dataset_uri, str):
            raise TypeError("dataset_uri must be a string or None")
        if k is not None and (isinstance(k, bool) or not isinstance(k, int) or k <= 0):
            raise ValueError("k must be a positive integer or None")

        parameters: dict[str, Any] = {}
        where = ""
        if dataset_uri:
            parameters["dataset_uid"] = vertex_uid(dataset_uri)
            where = "WHERE d.uid = $dataset_uid"
        limit = ""
        if k is not None:
            parameters["row_limit"] = k
            limit = "LIMIT $row_limit"
        query = f"""
MATCH (p:Pipeline)-[:IS_PART_OF]->(d:Dataset)
{where}
AND p.title IS NOT NULL
AND p.author IS NOT NULL
AND p.written_on_raw IS NOT NULL
AND p.votes IS NOT NULL
AND p.score IS NOT NULL
RETURN p.uri AS Pipeline_id,
       p.title AS Pipeline,
       p.author AS Author,
       p.written_on_raw AS Written_on,
       p.votes AS Number_of_votes,
       p.score AS Score
ORDER BY p.score DESC, p.uid ASC
{limit}
""".strip()
        # A query without dataset filtering cannot begin its predicate block
        # with AND.  Keep two explicit templates instead of weakening filters.
        if not where:
            query = query.replace("\nAND p.title", "\nWHERE p.title", 1)
        rows = self._client.run(query, parameters)
        return pd.DataFrame(rows, columns=_PIPELINE_COLUMNS)

    def find_candidate_competitions(
        self,
        problem_type: str,
        data_type: str,
        exclude_uri: str,
    ) -> list[str]:
        if not isinstance(problem_type, str) or not isinstance(data_type, str):
            raise TypeError("problem_type and data_type must be strings")
        rows = self._client.run(
            """
MATCH (d:Dataset)
WHERE d.problem_type = $problem_type
  AND d.data_type = $data_type
  AND d.uid <> $exclude_uid
RETURN d.uri AS competition_uri
ORDER BY d.uid ASC
""".strip(),
            {
                "data_type": data_type,
                "exclude_uid": vertex_uid(exclude_uri),
                "problem_type": problem_type,
            },
        )
        values: list[str] = []
        for row in rows:
            uri = row.get("competition_uri")
            if not isinstance(uri, str):
                raise TuGraphStoreError("Candidate competition URI must be a string")
            values.append(uri)
        return values

    def list_competitions(self) -> list[dict[str, Any]]:
        rows = self._client.run(
            """
MATCH (d:Dataset)
WHERE d.name IS NOT NULL
  AND d.problem_type IS NOT NULL
  AND d.data_type IS NOT NULL
RETURN d.uri AS comp_uri,
       d.name AS comp_name,
       d.problem_type AS problem_type,
       d.data_type AS data_type
ORDER BY d.uid ASC
""".strip(),
            {},
        )
        competitions: list[dict[str, Any]] = []
        for row in rows:
            values = {
                "comp_uri": row.get("comp_uri"),
                "comp_name": row.get("comp_name"),
                "problem_type": row.get("problem_type"),
                "data_type": row.get("data_type"),
            }
            if not all(isinstance(value, str) for value in values.values()):
                raise TuGraphStoreError("Competition fields must all be strings")
            values["problem_type"] = values["problem_type"].strip()
            values["data_type"] = values["data_type"].strip()
            competitions.append(values)
        return competitions

    def get_competition_name(self, competition_uri: str) -> str | None:
        rows = self._client.run(
            "MATCH (d:Dataset {uid: $dataset_uid}) RETURN d.name AS name",
            {"dataset_uid": vertex_uid(competition_uri)},
        )
        if not rows or rows[0].get("name") is None:
            return None
        if len(rows) != 1 or not isinstance(rows[0].get("name"), str):
            raise TuGraphStoreError("Dataset name query violated the unique string contract")
        return rows[0]["name"]

    def get_column_similarities(
        self,
        column_uri: str,
        relation: str,
    ) -> list[dict[str, Any]]:
        """Return directed RDF-star similarity edges with their certainty."""

        if relation not in _SIMILARITY_RELATIONS:
            raise ValueError(f"Unsupported similarity relation: {relation!r}")
        rows = self._client.run(
            f"""
MATCH (source:Column {{uid: $column_uid}})-[r:{relation}]->(target:Column)
RETURN target.uri AS target_uri, r.certainty AS certainty
ORDER BY target.uid ASC
""".strip(),
            {"column_uid": vertex_uid(column_uri)},
        )
        result: list[dict[str, Any]] = []
        for row in rows:
            target_uri = row.get("target_uri")
            certainty = row.get("certainty")
            if not isinstance(target_uri, str):
                raise TuGraphStoreError("Similarity target URI must be a string")
            if isinstance(certainty, bool) or not isinstance(certainty, (int, float)):
                raise TuGraphStoreError("Similarity certainty must be numeric")
            if not 0.0 <= float(certainty) <= 1.0:
                raise TuGraphStoreError("Similarity certainty is outside [0, 1]")
            result.append({"target_uri": target_uri, "certainty": float(certainty)})
        return result

    def get_competition_tables(self, competition_uri: str) -> list[dict[str, Any]]:
        rows = self._client.run(
            """
MATCH (c:Column)-[:IS_PART_OF]->(t:Table)-[:IS_PART_OF]->(d:Dataset {uid: $dataset_uid})
WHERE t.name IS NOT NULL
  AND c.name IS NOT NULL
  AND c.data_type IS NOT NULL
RETURN t.uid AS table_uid,
       t.uri AS table_uri,
       t.name AS table_name,
       c.uid AS column_uid,
       c.uri AS col_uri,
       c.name AS col_name,
       c.data_type AS data_type
ORDER BY t.uid ASC, c.uid ASC
""".strip(),
            {"dataset_uid": vertex_uid(competition_uri)},
        )
        tables: dict[str, dict[str, Any]] = {}
        for row in rows:
            table_uid = row.get("table_uid")
            if not isinstance(table_uid, str):
                raise TuGraphStoreError("Table UID must be a string")
            table = tables.setdefault(
                table_uid,
                {
                    "table_uri": row.get("table_uri"),
                    "table_name": row.get("table_name"),
                    "columns": [],
                },
            )
            table["columns"].append(
                {
                    "col_uri": row.get("col_uri"),
                    "col_name": row.get("col_name"),
                    "data_type": row.get("data_type"),
                }
            )
        return list(tables.values())

    def get_eda_insight(
        self,
        competition_uri: str,
        eda_type: str,
    ) -> dict[str, Any]:
        variants = {
            "pre_eda": (
                "HAS_PRELIMINARY_EDA_INSIGHT",
                "PreliminaryEDAInsight",
                {
                    "pre_eda_data_quality": "data_quality",
                    "pre_eda_basic_distribution": "basic_distribution",
                    "pre_eda_basic_dimensionality": "basic_dimensionality",
                },
            ),
            "deep_eda": (
                "HAS_IN_DEPTH_EDA_INSIGHT",
                "InDepthEDAInsight",
                {
                    "deep_eda_feature_relationships": "feature_relationships",
                    "deep_eda_complexity": "complexity",
                    "deep_eda_special_scenarios": "special_scenarios",
                },
            ),
        }
        try:
            relation, label, module_names = variants[eda_type]
        except KeyError as exc:
            raise ValueError("eda_type must be pre_eda or deep_eda") from exc
        rows = self._client.run(
            f"""
MATCH (d:Dataset {{uid: $dataset_uid}})-[:{relation}]->(e:{label})
RETURN e.payload_json AS payload_json
ORDER BY e.uid ASC
""".strip(),
            {"dataset_uid": vertex_uid(competition_uri)},
        )
        if not rows:
            return {}
        if len(rows) != 1:
            raise TuGraphStoreError(
                f"Dataset has {len(rows)} {eda_type} insight vertices; expected one"
            )
        payload_json = rows[0].get("payload_json")
        if not isinstance(payload_json, str):
            raise TuGraphStoreError("EDA payload_json must be a string")
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError as exc:
            raise TuGraphStoreError(f"EDA payload_json is invalid: {exc}") from exc
        if not isinstance(payload, dict):
            raise TuGraphStoreError("EDA payload_json must contain an object")
        if payload.get("eda_type") != eda_type:
            raise TuGraphStoreError("EDA payload type does not match its vertex label")

        def flatten(value: dict[str, Any], prefix: str = "") -> dict[str, Any]:
            result: dict[str, Any] = {}
            for name, item in value.items():
                field_path = f"{prefix}.{name}" if prefix else name
                if isinstance(item, dict):
                    result.update(flatten(item, field_path))
                else:
                    result[field_path] = item
            return result

        projected: dict[str, dict[str, Any]] = {}
        for source_name, output_name in module_names.items():
            if source_name not in payload:
                continue
            module = payload[source_name]
            if not isinstance(module, dict):
                raise TuGraphStoreError(f"EDA module {source_name} must be an object")
            allowed_fields = FIELD_WEIGHTS[output_name]
            projected[output_name] = {
                field_path: value
                for field_path, value in flatten(module).items()
                if field_path in allowed_fields
            }
        return projected

    def get_core_insights(self, pipeline_uri: str) -> pd.DataFrame:
        pipeline_uid = vertex_uid(pipeline_uri)
        rows = self._client.run(
            """
MATCH (p:Pipeline {uid: $pipeline_uid})-[:HAS_CORE_INSIGHT]->(i:CoreInsight)
RETURN i.uid AS insight_uid,
       i.uri AS insight_uri,
       i.insight_id AS Insight_ID,
       i.description AS Description,
       i.insight_type AS Insight_Type,
       i.effectiveness AS Effectiveness,
       i.evidence AS Evidence,
       i.phase AS Phase
ORDER BY Insight_ID ASC, insight_uri ASC
""".strip(),
            {"pipeline_uid": pipeline_uid},
        )
        insight_uids = [row.get("insight_uid") for row in rows]
        if any(not isinstance(uid, str) for uid in insight_uids):
            raise TuGraphStoreError("Core insight UID must be a string")
        if len(insight_uids) != len(set(insight_uids)):
            raise TuGraphStoreError("Core insight UID query returned duplicates")
        phases_by_uid: dict[str, list[Any]] = {}
        if insight_uids:
            phase_rows = self._client.run(
                """
MATCH (i:CoreInsight)-[:SPANS_PHASE]->(phase:Phase)
WHERE i.uid IN $insight_uids
RETURN i.uid AS insight_uid,
       phase.name AS phase_name
ORDER BY i.uid ASC, phase.name ASC
""".strip(),
                {"insight_uids": insight_uids},
            )
            for phase_row in phase_rows:
                uid = phase_row.get("insight_uid")
                phase_name = phase_row.get("phase_name")
                if uid not in insight_uids or not isinstance(phase_name, str):
                    raise TuGraphStoreError("Invalid spanning phases query result")
                phases_by_uid.setdefault(uid, []).append(phase_name)
        normalized: list[dict[str, Any]] = []
        for row in rows:
            phases = phases_by_uid.get(row["insight_uid"], [])
            normalized.append(
                {
                    "Insight_ID": row.get("Insight_ID"),
                    "Description": row.get("Description"),
                    "Insight_Type": row.get("Insight_Type"),
                    "Effectiveness": row.get("Effectiveness"),
                    "Evidence": row.get("Evidence"),
                    "Phase": row.get("Phase"),
                    "Spanning_Phases": ", ".join(
                        sorted({str(value) for value in phases if value is not None})
                    ),
                }
            )
        return pd.DataFrame(normalized, columns=_INSIGHT_COLUMNS)

    def get_competition_field(self, competition_uri: str, field: str) -> str | None:
        if field not in _COMPETITION_FIELDS:
            raise ValueError(
                f"Unsupported competition field {field!r}; "
                f"expected one of {sorted(_COMPETITION_FIELDS)}"
            )
        rows = self._client.run(
            f"MATCH (d:Dataset {{uid: $dataset_uid}}) RETURN d.{field} AS field_value",
            {"dataset_uid": vertex_uid(competition_uri)},
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise TuGraphStoreError(
                f"Dataset UID unexpectedly matched {len(rows)} vertices"
            )
        value = rows[0].get("field_value")
        if value is None:
            return None
        if not isinstance(value, str):
            raise TuGraphStoreError(f"Dataset field {field!r} must be a string")
        return value

    def get_insight_code(self, insight_uri: str) -> list[dict[str, Any]]:
        rows = self._client.run(
            """
MATCH (i:CoreInsight {uid: $insight_uid})-[:IMPLEMENTED_IN]->(s:Statement)
RETURN s.uri AS stmt_uri, s.text AS code_text, s.ordinal AS statement_order
ORDER BY s.ordinal ASC, s.uid ASC
""".strip(),
            {"insight_uid": vertex_uid(insight_uri)},
        )
        snippets: list[dict[str, Any]] = []
        for row in rows:
            order = row.get("statement_order")
            if isinstance(order, bool) or not isinstance(order, int):
                raise TuGraphStoreError("Statement order must be an integer")
            snippets.append(
                {
                    "stmt_uri": row.get("stmt_uri"),
                    "code_text": row.get("code_text"),
                    "order": order,
                }
            )
        return snippets

    def close(self) -> None:
        self._client.close()
