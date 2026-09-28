"""Convert existing Profile objects to storage-neutral CIR records.

This module is a side-by-side adapter.  The current RDF builder remains the
production path until golden-data parity has been established.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from sack.knowledge.graph.id_codec import normalize_uri, resource_id_to_uri
from sack.knowledge.graph.model import EdgeRecord, VertexRecord
from sack.knowledge.kg_governor.data_global_schema_builder.utils.utils import generate_label


SACK_ONTOLOGY_PREFIX = "http://sack.local/ontology/"
SIMILARITY_EDGE_TYPES = {"HAS_CONTENT_SIMILARITY", "HAS_LABEL_SIMILARITY"}


class GlobalSchemaBuildError(ValueError):
    """Raised when source Profiles cannot form one deterministic graph."""


@dataclass(frozen=True, slots=True)
class GlobalSchemaRecords:
    vertices: tuple[VertexRecord, ...]
    edges: tuple[EdgeRecord, ...]


def _uri(resource_id_or_uri: str) -> str:
    if not isinstance(resource_id_or_uri, str) or not resource_id_or_uri:
        raise GlobalSchemaBuildError("Profile resource id must be a non-empty string")
    if "://" in resource_id_or_uri:
        return normalize_uri(resource_id_or_uri)
    return resource_id_to_uri(resource_id_or_uri)


def _display_label(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GlobalSchemaBuildError("Profile name must be a non-empty string")
    return generate_label(value, "en").get_text()


def _optional_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise GlobalSchemaBuildError(f"{field_name} must be an integer, not boolean")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise GlobalSchemaBuildError(f"{field_name} must be an integer") from exc
    if not math.isfinite(numeric) or not numeric.is_integer():
        raise GlobalSchemaBuildError(f"{field_name} must be a finite integer")
    return int(numeric)


def _optional_float(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise GlobalSchemaBuildError(f"{field_name} must be numeric, not boolean")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise GlobalSchemaBuildError(f"{field_name} must be numeric") from exc
    if not math.isfinite(numeric):
        raise GlobalSchemaBuildError(f"{field_name} must be finite")
    return numeric


def _compact(properties: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in properties.items() if value is not None}


def _rdf_types(label: str) -> str:
    return json.dumps(
        [f"{SACK_ONTOLOGY_PREFIX}{label}"],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _profile_mapping(profile: Mapping[str, Any] | Any) -> Mapping[str, Any]:
    if isinstance(profile, Mapping):
        return profile
    to_dict = getattr(profile, "to_dict", None)
    if callable(to_dict):
        result = to_dict()
        if isinstance(result, Mapping):
            return result
    raise GlobalSchemaBuildError(
        f"Expected a mapping or Profile with to_dict(), got {type(profile).__name__}"
    )


def _structured_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True)


class _RecordAccumulator:
    def __init__(self) -> None:
        self.vertices: dict[str, VertexRecord] = {}
        self.edges: dict[str, EdgeRecord] = {}

    def add_vertex(self, record: VertexRecord) -> None:
        existing = self.vertices.get(record.uid)
        if existing is not None and existing != record:
            raise GlobalSchemaBuildError(
                f"Conflicting records for vertex {record.uri}: {existing.to_dict()} != {record.to_dict()}"
            )
        self.vertices[record.uid] = record

    def add_edge(self, record: EdgeRecord) -> None:
        existing = self.edges.get(record.edge_uid)
        if existing is not None and existing != record:
            raise GlobalSchemaBuildError(
                f"Conflicting records for edge {record.edge_uid}"
            )
        self.edges[record.edge_uid] = record

    def result(self) -> GlobalSchemaRecords:
        return GlobalSchemaRecords(
            vertices=tuple(sorted(self.vertices.values(), key=lambda item: (item.label, item.uid))),
            edges=tuple(sorted(self.edges.values(), key=lambda item: (item.edge_type, item.edge_uid))),
        )


def _membership_edge(
    source: VertexRecord,
    target: VertexRecord,
    build_id: str,
) -> EdgeRecord:
    return EdgeRecord.from_endpoints(
        edge_type="IS_PART_OF",
        src_uid=source.uid,
        dst_uid=target.uid,
        properties={},
        build_id=build_id,
    )


def _column_vertex(profile: Any, build_id: str) -> VertexRecord:
    properties = _compact(
        {
            "name": profile.get_column_name(),
            "display_label": _display_label(profile.get_column_name()),
            "rdf_types_json": _rdf_types("Column"),
            "data_type": profile.get_data_type(),
            "total_count": _optional_int(profile.get_total_values_count(), "total_values_count"),
            "distinct_count": _optional_int(
                profile.get_distinct_values_count(), "distinct_values_count"
            ),
            "missing_count": _optional_int(
                profile.get_missing_values_count(), "missing_values_count"
            ),
            "median": _optional_float(profile.get_median(), "median"),
            "min_value": _optional_float(profile.get_min_value(), "min_value"),
            "max_value": _optional_float(profile.get_max_value(), "max_value"),
            "true_ratio": _optional_float(profile.get_true_ratio(), "true_ratio"),
        }
    )
    return VertexRecord.from_uri(
        uri=_uri(profile.get_column_id()),
        label="Column",
        properties=properties,
        build_id=build_id,
    )


def _table_vertex(profile: Any, build_id: str) -> VertexRecord:
    name = profile.get_table_name()
    return VertexRecord.from_uri(
        uri=_uri(profile.get_table_id()),
        label="Table",
        properties=_compact(
            {
                "name": name,
                "display_label": _display_label(name),
                "rdf_types_json": _rdf_types("Table"),
                "file_path": profile.get_path(),
            }
        ),
        build_id=build_id,
    )


def _dataset_vertex(
    profile: Any,
    competition_profile: Mapping[str, Any] | Any | None,
    build_id: str,
) -> VertexRecord:
    metadata = {} if competition_profile is None else _profile_mapping(competition_profile)
    structured = metadata.get("structured_elements") or {}
    if not isinstance(structured, Mapping):
        raise GlobalSchemaBuildError("structured_elements must be an object")
    name = profile.get_dataset_name()
    return VertexRecord.from_uri(
        uri=_uri(profile.get_dataset_id()),
        label="Dataset",
        properties=_compact(
            {
                "name": name,
                "display_label": _display_label(name),
                "rdf_types_json": _rdf_types("Dataset"),
                "overview": metadata.get("overview"),
                "data_description": metadata.get("data_description"),
                "problem_type": _structured_value(structured.get("problem_type")),
                "domain": _structured_value(structured.get("domain")),
                "data_type": _structured_value(structured.get("data_type")),
                "difficulty": _structured_value(structured.get("difficulty")),
            }
        ),
        build_id=build_id,
    )


def _source_vertex(profile: Any, build_id: str) -> VertexRecord:
    name = profile.get_data_source()
    return VertexRecord.from_uri(
        uri=_uri(name),
        label="Source",
        properties={
            "name": name,
            "display_label": _display_label(name),
            "rdf_types_json": _rdf_types("Source"),
        },
        build_id=build_id,
    )


def _eda_vertex(profile: Mapping[str, Any] | Any, dataset_name: str, build_id: str) -> VertexRecord:
    data = _profile_mapping(profile)
    eda_type = data.get("eda_type")
    if eda_type not in {"pre_eda", "deep_eda"}:
        raise GlobalSchemaBuildError(f"Unsupported EDA type: {eda_type!r}")
    eda_id = data.get("eda_id")
    if not isinstance(eda_id, str) or not eda_id:
        raise GlobalSchemaBuildError("EDA profile is missing eda_id")
    label = "PreliminaryEDAInsight" if eda_type == "pre_eda" else "InDepthEDAInsight"
    name = f"{dataset_name}_{eda_type}"
    return VertexRecord.from_uri(
        uri=_uri(eda_id),
        label=label,
        properties={
            "name": name,
            "display_label": _display_label(
                f"{dataset_name} {eda_type.replace('_', ' ').title()} Insight"
            ),
            "rdf_types_json": _rdf_types(label),
            "payload_json": json.dumps(
                dict(data),
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
        },
        build_id=build_id,
    )


def build_global_schema_records(
    column_profiles: Sequence[Any],
    *,
    build_id: str,
    competition_profiles: Mapping[str, Mapping[str, Any] | Any] | None = None,
    eda_profiles: Mapping[str, Iterable[Mapping[str, Any] | Any]] | None = None,
) -> GlobalSchemaRecords:
    """Build Source/Dataset/Table/Column/EDA vertices and membership edges."""

    competition_profiles = competition_profiles or {}
    eda_profiles = eda_profiles or {}
    accumulator = _RecordAccumulator()
    processed_eda_datasets: set[str] = set()

    for profile in sorted(column_profiles, key=lambda item: item.get_column_id()):
        column = _column_vertex(profile, build_id)
        table = _table_vertex(profile, build_id)
        dataset = _dataset_vertex(
            profile,
            competition_profiles.get(profile.get_dataset_id()),
            build_id,
        )
        source = _source_vertex(profile, build_id)

        for record in (column, table, dataset, source):
            accumulator.add_vertex(record)
        for relation in (
            _membership_edge(column, table, build_id),
            _membership_edge(table, dataset, build_id),
            _membership_edge(dataset, source, build_id),
        ):
            accumulator.add_edge(relation)

        dataset_id = profile.get_dataset_id()
        if dataset_id in processed_eda_datasets:
            continue
        processed_eda_datasets.add(dataset_id)
        for eda_profile in eda_profiles.get(dataset_id, ()):
            eda = _eda_vertex(eda_profile, profile.get_dataset_name(), build_id)
            accumulator.add_vertex(eda)
            relation_type = (
                "HAS_PRELIMINARY_EDA_INSIGHT"
                if eda.label == "PreliminaryEDAInsight"
                else "HAS_IN_DEPTH_EDA_INSIGHT"
            )
            accumulator.add_edge(
                EdgeRecord.from_endpoints(
                    edge_type=relation_type,
                    src_uid=dataset.uid,
                    dst_uid=eda.uid,
                    properties={},
                    build_id=build_id,
                )
            )

    return accumulator.result()


def build_similarity_edges(
    first_column_profile: Any,
    second_column_profile: Any,
    *,
    edge_type: str,
    certainty: float,
    build_id: str,
) -> tuple[EdgeRecord, EdgeRecord]:
    """Map one RDF-star similarity assertion to the current two directed edges."""

    if edge_type not in SIMILARITY_EDGE_TYPES:
        raise GlobalSchemaBuildError(f"Unsupported similarity edge type: {edge_type}")
    score = _optional_float(certainty, "certainty")
    if score is None or not 0.0 <= score <= 1.0:
        raise GlobalSchemaBuildError("certainty must be between 0 and 1")

    first = VertexRecord.from_uri(
        uri=_uri(first_column_profile.get_column_id()),
        label="Column",
        properties={},
        build_id=build_id,
    )
    second = VertexRecord.from_uri(
        uri=_uri(second_column_profile.get_column_id()),
        label="Column",
        properties={},
        build_id=build_id,
    )
    forward = EdgeRecord.from_endpoints(
        edge_type=edge_type,
        src_uid=first.uid,
        dst_uid=second.uid,
        properties={"certainty": score},
        build_id=build_id,
    )
    reverse = EdgeRecord.from_endpoints(
        edge_type=edge_type,
        src_uid=second.uid,
        dst_uid=first.uid,
        properties={"certainty": score},
        build_id=build_id,
    )
    return forward, reverse
