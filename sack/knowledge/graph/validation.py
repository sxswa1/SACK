"""Whole-graph validation for canonical intermediate records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from sack.knowledge.graph.model import EdgeRecord, VertexRecord
from sack.knowledge.graph.schema_registry import (
    FieldType,
    PropertySpec,
    get_edge_schema,
    get_vertex_schema,
)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    record_id: str | None = None


@dataclass(slots=True)
class ValidationReport:
    vertex_count: int = 0
    edge_count: int = 0
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def add_error(self, code: str, message: str, record_id: str | None = None) -> None:
        self.errors.append(ValidationIssue(code, message, record_id))

    def add_warning(self, code: str, message: str, record_id: str | None = None) -> None:
        self.warnings.append(ValidationIssue(code, message, record_id))


def _matches_type(value: object, spec: PropertySpec) -> bool:
    if spec.field_type == FieldType.STRING or spec.field_type == FieldType.DATETIME:
        return isinstance(value, str)
    if spec.field_type == FieldType.BOOL:
        return isinstance(value, bool)
    if spec.field_type == FieldType.INT64:
        return isinstance(value, int) and not isinstance(value, bool)
    if spec.field_type == FieldType.DOUBLE:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False


def _validate_properties(
    *,
    values: dict[str, object],
    specs: Mapping[str, PropertySpec],
    report: ValidationReport,
    record_id: str,
) -> None:
    unexpected = sorted(set(values) - set(specs))
    for name in unexpected:
        report.add_error(
            "unknown_property",
            f"Property {name!r} is not declared by the schema registry",
            record_id,
        )
    for name, spec in specs.items():
        if spec.required and name not in values:
            report.add_error(
                "missing_required_property",
                f"Required property {name!r} is missing",
                record_id,
            )
        if name in values and values[name] is not None and not _matches_type(values[name], spec):
            report.add_error(
                "property_type_mismatch",
                f"Property {name!r} must be {spec.field_type.value}",
                record_id,
            )


def validate_graph(
    vertices: Iterable[VertexRecord],
    edges: Iterable[EdgeRecord],
) -> ValidationReport:
    """Validate referential, schema, RDF-star, and Named Graph invariants."""

    report = ValidationReport()
    vertex_by_uid: dict[str, VertexRecord] = {}
    edge_by_uid: dict[str, EdgeRecord] = {}

    for vertex in vertices:
        report.vertex_count += 1
        previous = vertex_by_uid.get(vertex.uid)
        if previous is not None:
            report.add_error(
                "duplicate_vertex_uid",
                "Duplicate vertex UID; builders must merge deterministically",
                vertex.uid,
            )
            continue
        vertex_by_uid[vertex.uid] = vertex

        try:
            schema = get_vertex_schema(vertex.label)
        except KeyError as exc:
            report.add_error("unknown_vertex_label", str(exc), vertex.uid)
            continue
        _validate_properties(
            values={
                "uid": vertex.uid,
                "uri": vertex.uri,
                "build_id": vertex.build_id,
                **({"source_hash": vertex.source_hash} if vertex.source_hash is not None else {}),
                **vertex.properties,
            },
            specs=schema.properties,
            report=report,
            record_id=vertex.uid,
        )

    for edge in edges:
        report.edge_count += 1
        if edge.edge_uid in edge_by_uid:
            report.add_error(
                "duplicate_edge_uid",
                "Duplicate edge UID; parallel edges need a stable discriminator",
                edge.edge_uid,
            )
            continue
        edge_by_uid[edge.edge_uid] = edge

        source = vertex_by_uid.get(edge.src_uid)
        target = vertex_by_uid.get(edge.dst_uid)
        if source is None:
            report.add_error("missing_source_vertex", "Edge source does not exist", edge.edge_uid)
        if target is None:
            report.add_error("missing_target_vertex", "Edge target does not exist", edge.edge_uid)

        try:
            schema = get_edge_schema(edge.edge_type)
        except KeyError as exc:
            report.add_error("unknown_edge_label", str(exc), edge.edge_uid)
            continue

        _validate_properties(
            values={
                "edge_uid": edge.edge_uid,
                "build_id": edge.build_id,
                **({"scope_uid": edge.scope_uid} if edge.scope_uid is not None else {}),
                **edge.properties,
            },
            specs=schema.properties,
            report=report,
            record_id=edge.edge_uid,
        )
        if schema.scope_required and edge.scope_uid is None:
            report.add_error(
                "missing_pipeline_scope",
                f"{edge.edge_type} must retain its Named Graph Pipeline scope",
                edge.edge_uid,
            )

        if source is not None and target is not None:
            endpoints = (source.label, target.label)
            if endpoints not in schema.endpoint_pairs:
                report.add_error(
                    "invalid_edge_endpoints",
                    f"{edge.edge_type} does not allow {source.label}->{target.label}",
                    edge.edge_uid,
                )

        if edge.scope_uid is not None:
            scope = vertex_by_uid.get(edge.scope_uid)
            if scope is None:
                report.add_error(
                    "missing_scope_vertex",
                    "Edge scope does not reference an existing Pipeline",
                    edge.edge_uid,
                )
            elif scope.label != "Pipeline":
                report.add_error(
                    "invalid_scope_label",
                    f"Edge scope must be Pipeline, not {scope.label}",
                    edge.edge_uid,
                )
            for endpoint in (source, target):
                if endpoint is None or endpoint.label != "Statement":
                    continue
                statement_scope = endpoint.properties.get("pipeline_uid")
                if statement_scope is not None and statement_scope != edge.scope_uid:
                    report.add_error(
                        "statement_scope_mismatch",
                        "Statement pipeline_uid differs from edge scope_uid",
                        edge.edge_uid,
                    )

        if edge.edge_type in {"HAS_CONTENT_SIMILARITY", "HAS_LABEL_SIMILARITY"}:
            certainty = edge.properties.get("certainty")
            if isinstance(certainty, (int, float)) and not isinstance(certainty, bool):
                if not 0.0 <= float(certainty) <= 1.0:
                    report.add_error(
                        "certainty_out_of_range",
                        "Similarity certainty must be between 0 and 1",
                        edge.edge_uid,
                    )

    similarity_edges: dict[tuple[str, str, str], EdgeRecord] = {}
    for edge in edge_by_uid.values():
        if edge.edge_type not in {"HAS_CONTENT_SIMILARITY", "HAS_LABEL_SIMILARITY"}:
            continue
        key = (edge.edge_type, edge.src_uid, edge.dst_uid)
        if key in similarity_edges:
            report.add_error(
                "duplicate_similarity_pair",
                "Only one similarity edge is allowed per type and directed Column pair",
                edge.edge_uid,
            )
        else:
            similarity_edges[key] = edge
    for (edge_type, source_uid, target_uid), forward in similarity_edges.items():
        reverse = similarity_edges.get((edge_type, target_uid, source_uid))
        if reverse is None:
            report.add_error(
                "missing_reverse_similarity",
                "Similarity edge must retain its reverse direction",
                forward.edge_uid,
            )
        elif reverse.properties.get("certainty") != forward.properties.get("certainty"):
            report.add_error(
                "reverse_similarity_score_mismatch",
                "Similarity edge and its reverse must have the same certainty",
                forward.edge_uid,
            )

    return report
