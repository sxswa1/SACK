"""Deterministic merge rules for canonical records from independent builders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from sack.knowledge.graph.model import EdgeRecord, VertexRecord


class RecordMergeError(ValueError):
    """Raised when two records claim the same identity with different meaning."""


@dataclass(frozen=True, slots=True)
class MergedGraphRecords:
    vertices: tuple[VertexRecord, ...]
    edges: tuple[EdgeRecord, ...]


def _merge_properties(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
    *,
    record_id: str,
) -> dict[str, Any]:
    merged = dict(first)
    for key, value in second.items():
        if key in merged and merged[key] != value:
            raise RecordMergeError(
                f"Conflicting property {key!r} for record {record_id}: "
                f"{merged[key]!r} != {value!r}"
            )
        merged[key] = value
    return merged


def merge_vertex_records(first: VertexRecord, second: VertexRecord) -> VertexRecord:
    if first.uid != second.uid:
        raise RecordMergeError("Cannot merge vertices with different UIDs")
    if first.uri != second.uri or first.label != second.label:
        raise RecordMergeError(
            f"Vertex identity collision for {first.uid}: "
            f"{first.label}:{first.uri} != {second.label}:{second.uri}"
        )
    if first.build_id != second.build_id:
        raise RecordMergeError(
            f"Vertex {first.uid} belongs to two build IDs: "
            f"{first.build_id!r} and {second.build_id!r}"
        )
    if (
        first.source_hash is not None
        and second.source_hash is not None
        and first.source_hash != second.source_hash
    ):
        raise RecordMergeError(f"Conflicting source_hash for vertex {first.uid}")
    return VertexRecord(
        uid=first.uid,
        uri=first.uri,
        label=first.label,
        properties=_merge_properties(
            first.properties,
            second.properties,
            record_id=first.uid,
        ),
        build_id=first.build_id,
        source_hash=first.source_hash or second.source_hash,
    )


def merge_edge_records(first: EdgeRecord, second: EdgeRecord) -> EdgeRecord:
    if first.edge_uid != second.edge_uid:
        raise RecordMergeError("Cannot merge edges with different UIDs")
    identity_first = (
        first.edge_type,
        first.src_uid,
        first.dst_uid,
        first.scope_uid,
        first.build_id,
    )
    identity_second = (
        second.edge_type,
        second.src_uid,
        second.dst_uid,
        second.scope_uid,
        second.build_id,
    )
    if identity_first != identity_second:
        raise RecordMergeError(f"Edge identity collision for {first.edge_uid}")
    return EdgeRecord(
        edge_uid=first.edge_uid,
        edge_type=first.edge_type,
        src_uid=first.src_uid,
        dst_uid=first.dst_uid,
        properties=_merge_properties(
            first.properties,
            second.properties,
            record_id=first.edge_uid,
        ),
        build_id=first.build_id,
        scope_uid=first.scope_uid,
    )


def merge_graph_records(
    *,
    vertex_groups: Iterable[Iterable[VertexRecord]],
    edge_groups: Iterable[Iterable[EdgeRecord]],
) -> MergedGraphRecords:
    vertices: dict[str, VertexRecord] = {}
    edges: dict[str, EdgeRecord] = {}

    for group in vertex_groups:
        for vertex in group:
            existing = vertices.get(vertex.uid)
            vertices[vertex.uid] = (
                vertex if existing is None else merge_vertex_records(existing, vertex)
            )
    for group in edge_groups:
        for edge in group:
            existing = edges.get(edge.edge_uid)
            edges[edge.edge_uid] = (
                edge if existing is None else merge_edge_records(existing, edge)
            )
    return MergedGraphRecords(
        vertices=tuple(sorted(vertices.values(), key=lambda item: (item.label, item.uid))),
        edges=tuple(sorted(edges.values(), key=lambda item: (item.edge_type, item.edge_uid))),
    )
