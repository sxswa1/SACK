"""Versioned structural schema shared by CIR validation and graph sinks.

This first registry captures stable labels, endpoint constraints, and common
fields.  Profile-specific optional EDA fields will be added only after their
current GraphDB output has been frozen as a golden fixture.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


SCHEMA_VERSION = "1.0.0-draft.1"


class FieldType(str, Enum):
    STRING = "STRING"
    BOOL = "BOOL"
    INT64 = "INT64"
    DOUBLE = "DOUBLE"
    DATETIME = "DATETIME"


@dataclass(frozen=True, slots=True)
class PropertySpec:
    field_type: FieldType
    required: bool = False
    indexed: bool = False
    unique: bool = False

    def __post_init__(self) -> None:
        if self.unique and not self.indexed:
            raise ValueError("A unique property must also be indexed")


@dataclass(frozen=True, slots=True)
class VertexSchema:
    label: str
    properties: Mapping[str, PropertySpec]


@dataclass(frozen=True, slots=True)
class EdgeSchema:
    label: str
    endpoint_pairs: frozenset[tuple[str, str]]
    properties: Mapping[str, PropertySpec]
    scope_required: bool = False

    @property
    def src_labels(self) -> frozenset[str]:
        return frozenset(source for source, _ in self.endpoint_pairs)

    @property
    def dst_labels(self) -> frozenset[str]:
        return frozenset(target for _, target in self.endpoint_pairs)


def _properties(**values: PropertySpec) -> Mapping[str, PropertySpec]:
    return MappingProxyType(dict(values))


COMMON_VERTEX_PROPERTIES = _properties(
    uid=PropertySpec(FieldType.STRING, required=True, indexed=True),
    uri=PropertySpec(FieldType.STRING, required=True),
    build_id=PropertySpec(FieldType.STRING, required=True, indexed=True),
    source_hash=PropertySpec(FieldType.STRING),
    name=PropertySpec(FieldType.STRING),
    display_label=PropertySpec(FieldType.STRING),
    rdf_types_json=PropertySpec(FieldType.STRING),
)


def _vertex(label: str, **properties: PropertySpec) -> VertexSchema:
    merged = dict(COMMON_VERTEX_PROPERTIES)
    merged.update(properties)
    return VertexSchema(label=label, properties=MappingProxyType(merged))


VERTEX_SCHEMAS: Mapping[str, VertexSchema] = MappingProxyType(
    {
        schema.label: schema
        for schema in (
            _vertex("Source"),
            _vertex(
                "Dataset",
                overview=PropertySpec(FieldType.STRING),
                data_description=PropertySpec(FieldType.STRING),
                problem_type=PropertySpec(FieldType.STRING),
                domain=PropertySpec(FieldType.STRING),
                data_type=PropertySpec(FieldType.STRING),
                difficulty=PropertySpec(FieldType.STRING),
            ),
            _vertex("Table", file_path=PropertySpec(FieldType.STRING)),
            _vertex(
                "Column",
                data_type=PropertySpec(FieldType.STRING),
                total_count=PropertySpec(FieldType.INT64),
                distinct_count=PropertySpec(FieldType.INT64),
                missing_count=PropertySpec(FieldType.INT64),
                median=PropertySpec(FieldType.DOUBLE),
                min_value=PropertySpec(FieldType.DOUBLE),
                max_value=PropertySpec(FieldType.DOUBLE),
                true_ratio=PropertySpec(FieldType.DOUBLE),
            ),
            _vertex("PreliminaryEDAInsight", payload_json=PropertySpec(FieldType.STRING)),
            _vertex("InDepthEDAInsight", payload_json=PropertySpec(FieldType.STRING)),
            _vertex(
                "Pipeline",
                title=PropertySpec(FieldType.STRING),
                author=PropertySpec(FieldType.STRING),
                votes=PropertySpec(FieldType.INT64),
                written_on_raw=PropertySpec(FieldType.STRING),
                written_on_ts=PropertySpec(FieldType.DATETIME),
                source_url=PropertySpec(FieldType.STRING),
                score=PropertySpec(FieldType.DOUBLE),
            ),
            _vertex(
                "Statement",
                text=PropertySpec(FieldType.STRING),
                phase=PropertySpec(FieldType.STRING),
                ordinal=PropertySpec(FieldType.INT64),
                pipeline_uid=PropertySpec(FieldType.STRING, indexed=True),
            ),
            _vertex("Library", qualified_name=PropertySpec(FieldType.STRING)),
            _vertex("Package", qualified_name=PropertySpec(FieldType.STRING)),
            _vertex("Class", qualified_name=PropertySpec(FieldType.STRING)),
            _vertex("Function", qualified_name=PropertySpec(FieldType.STRING)),
            _vertex("API", qualified_name=PropertySpec(FieldType.STRING)),
            _vertex("Parameter", name=PropertySpec(FieldType.STRING, required=True)),
            _vertex("Tag", normalized_name=PropertySpec(FieldType.STRING, indexed=True)),
            _vertex(
                "CoreInsight",
                insight_id=PropertySpec(FieldType.STRING),
                description=PropertySpec(FieldType.STRING),
                insight_type=PropertySpec(FieldType.STRING),
                effectiveness=PropertySpec(FieldType.STRING),
                significance=PropertySpec(FieldType.STRING),
                transferability=PropertySpec(FieldType.STRING),
                evidence=PropertySpec(FieldType.STRING),
                phase=PropertySpec(FieldType.STRING),
            ),
            _vertex("Phase", sort_order=PropertySpec(FieldType.INT64)),
            _vertex("ControlFlow", kind=PropertySpec(FieldType.STRING)),
            _vertex(
                "OntologyTerm",
                term_uri=PropertySpec(FieldType.STRING),
                term_kind=PropertySpec(FieldType.STRING),
            ),
        )
    }
)


def _edge(
    label: str,
    endpoint_pairs: set[tuple[str, str]],
    *,
    scope_required: bool = False,
    **properties: PropertySpec,
) -> EdgeSchema:
    base = {
        "edge_uid": PropertySpec(
            FieldType.STRING,
            required=True,
            indexed=True,
            unique=True,
        ),
        "build_id": PropertySpec(FieldType.STRING, required=True, indexed=True),
        "scope_uid": PropertySpec(FieldType.STRING, indexed=True),
    }
    base.update(properties)
    return EdgeSchema(
        label=label,
        endpoint_pairs=frozenset(endpoint_pairs),
        properties=MappingProxyType(base),
        scope_required=scope_required,
    )


_API_LABELS = {"Library", "Package", "Class", "Function", "API"}
_API_PART_OF_PAIRS = {
    (child, parent)
    for child in _API_LABELS
    for parent in _API_LABELS
}

EDGE_SCHEMAS: Mapping[str, EdgeSchema] = MappingProxyType(
    {
        schema.label: schema
        for schema in (
            _edge(
                "IS_PART_OF",
                {
                    ("Column", "Table"),
                    ("Table", "Dataset"),
                    ("Dataset", "Source"),
                    ("Pipeline", "Dataset"),
                    ("Statement", "Pipeline"),
                }
                | _API_PART_OF_PAIRS,
            ),
            _edge(
                "HAS_CONTENT_SIMILARITY",
                {("Column", "Column")},
                certainty=PropertySpec(FieldType.DOUBLE, required=True),
            ),
            _edge(
                "HAS_LABEL_SIMILARITY",
                {("Column", "Column")},
                certainty=PropertySpec(FieldType.DOUBLE, required=True),
            ),
            _edge("HAS_PRELIMINARY_EDA_INSIGHT", {("Dataset", "PreliminaryEDAInsight")}),
            _edge("HAS_IN_DEPTH_EDA_INSIGHT", {("Dataset", "InDepthEDAInsight")}),
            _edge("NEXT_STATEMENT", {("Statement", "Statement")}, scope_required=True),
            _edge("DATA_FLOW_TO", {("Statement", "Statement")}, scope_required=True),
            _edge("IN_CONTROL_FLOW", {("Statement", "ControlFlow")}, scope_required=True),
            _edge("CALLS_FUNCTION", {("Statement", "Function")}, scope_required=True),
            _edge("CALLS_CLASS", {("Statement", "Class")}, scope_required=True),
            _edge("CALLS_PACKAGE", {("Statement", "Package")}, scope_required=True),
            _edge("CALLS_LIBRARY", {("Statement", "Library")}, scope_required=True),
            _edge(
                "CALLS_API",
                {("Statement", label) for label in _API_LABELS},
                scope_required=True,
            ),
            _edge("READS_TABLE", {("Statement", "Table")}, scope_required=True),
            _edge("READS_COLUMN", {("Statement", "Column")}, scope_required=True),
            _edge(
                "HAS_PARAMETER",
                {("Statement", "Parameter")},
                scope_required=True,
                value=PropertySpec(FieldType.STRING),
                value_type=PropertySpec(FieldType.STRING),
            ),
            _edge("HAS_TAG", {("Pipeline", "Tag")}),
            _edge("HAS_CORE_INSIGHT", {("Pipeline", "CoreInsight")}, scope_required=True),
            _edge("IMPLEMENTED_IN", {("CoreInsight", "Statement")}, scope_required=True),
            _edge("SPANS_PHASE", {("CoreInsight", "Phase")}),
            _edge("SUBCLASS_OF", {("OntologyTerm", "OntologyTerm")}),
        )
    }
)


def get_vertex_schema(label: str) -> VertexSchema:
    try:
        return VERTEX_SCHEMAS[label]
    except KeyError as exc:
        raise KeyError(f"Unknown vertex label: {label}") from exc


def get_edge_schema(label: str) -> EdgeSchema:
    try:
        return EDGE_SCHEMAS[label]
    except KeyError as exc:
        raise KeyError(f"Unknown edge label: {label}") from exc
