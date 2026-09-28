"""Export canonical graph records in TuGraph's lossless JSON-line format.

TuGraph import files describe columns in ``import.config.json``.  Vertex rows
use the stable ``uid`` as their primary key.  Edge rows are partitioned by
edge label and concrete endpoint-label pair because each TuGraph file entry
must declare exactly one ``SRC_ID`` label and one ``DST_ID`` label.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from sack.knowledge.graph.id_codec import ID_CODEC_VERSION
from sack.knowledge.graph.model import EdgeRecord, VertexRecord
from sack.knowledge.graph.schema_registry import (
    EDGE_SCHEMAS,
    VERTEX_SCHEMAS,
    EdgeSchema,
    PropertySpec,
    VertexSchema,
)
from sack.knowledge.graph.validation import validate_graph


class TuGraphExportError(ValueError):
    """Raised when CIR records cannot be exported without semantic loss."""


TUGRAPH_TARGET_VERSION = "4.5.2"


@dataclass(frozen=True, slots=True)
class TuGraphArtifact:
    relative_path: str
    row_count: int
    byte_count: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "byte_count": self.byte_count,
            "relative_path": self.relative_path,
            "row_count": self.row_count,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class TuGraphExportManifest:
    build_id: str
    artifacts: Sequence[TuGraphArtifact]
    vertex_count: int
    edge_count: int
    source_schema_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifacts": [
                item.to_dict()
                for item in sorted(self.artifacts, key=lambda value: value.relative_path)
            ],
            "build_id": self.build_id,
            "edge_count": self.edge_count,
            "export_format": "TUGRAPH_JSON_LINES",
            "id_codec_version": ID_CODEC_VERSION,
            "manifest_version": "1.0",
            "source_schema_version": self.source_schema_version,
            "target": f"TuGraph {TUGRAPH_TARGET_VERSION}",
            "vertex_count": self.vertex_count,
        }


def _file_stem(label: str) -> str:
    first_pass = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", label)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", first_pass).lower()


def _property_config(name: str, spec: PropertySpec, *, primary: bool = False) -> dict[str, Any]:
    value: dict[str, Any] = {"name": name, "type": spec.field_type.value}
    if not spec.required:
        value["optional"] = True
    if spec.indexed and not primary:
        value["index"] = True
    if spec.unique:
        value["unique"] = True
    return value


def _vertex_schema_config(schema: VertexSchema) -> dict[str, Any]:
    return {
        "label": schema.label,
        "primary": "uid",
        "properties": [
            _property_config(name, spec, primary=name == "uid")
            for name, spec in schema.properties.items()
        ],
        "type": "VERTEX",
    }


def _edge_schema_config(schema: EdgeSchema) -> dict[str, Any]:
    properties = [
        _property_config(name, spec)
        for name, spec in schema.properties.items()
    ]
    # TuGraph 4.5.2 offline import rejects unique edge indexes.  CIR
    # validation still enforces edge_uid uniqueness before export.
    for property_config in properties:
        property_config.pop("unique", None)
    return {
        "constraints": [list(pair) for pair in sorted(schema.endpoint_pairs)],
        "label": schema.label,
        "properties": properties,
        "type": "EDGE",
    }


def build_tugraph_schema_config() -> list[dict[str, Any]]:
    """Translate the registry into TuGraph's documented strong schema."""

    vertices = [
        _vertex_schema_config(VERTEX_SCHEMAS[label])
        for label in sorted(VERTEX_SCHEMAS)
    ]
    edges = [
        _edge_schema_config(EDGE_SCHEMAS[label])
        for label in sorted(EDGE_SCHEMAS)
    ]
    return vertices + edges


def _vertex_values(record: VertexRecord, schema: VertexSchema) -> Mapping[str, Any]:
    return {
        "uid": record.uid,
        "uri": record.uri,
        "build_id": record.build_id,
        **({"source_hash": record.source_hash} if record.source_hash is not None else {}),
        **record.properties,
    }


def _edge_values(record: EdgeRecord) -> Mapping[str, Any]:
    return {
        "edge_uid": record.edge_uid,
        "build_id": record.build_id,
        **({"scope_uid": record.scope_uid} if record.scope_uid is not None else {}),
        **record.properties,
    }


def _write_json_lines(
    root: Path,
    relative_path: str,
    rows: Iterable[Sequence[Any]],
) -> TuGraphArtifact:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    row_count = 0
    byte_count = 0
    with path.open("wb") as stream:
        for row in rows:
            payload = (
                json.dumps(
                    list(row),
                    allow_nan=False,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
            stream.write(payload)
            digest.update(payload)
            row_count += 1
            byte_count += len(payload)
    return TuGraphArtifact(relative_path, row_count, byte_count, digest.hexdigest())


def _write_json_object(path: Path, value: Mapping[str, Any]) -> TuGraphArtifact:
    payload = (
        json.dumps(value, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    path.write_bytes(payload)
    return TuGraphArtifact(
        relative_path=path.name,
        row_count=1,
        byte_count=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def export_tugraph_package(
    vertices: Iterable[VertexRecord],
    edges: Iterable[EdgeRecord],
    output_dir: str | Path,
    *,
    source_schema_version: str,
) -> TuGraphExportManifest:
    """Write a new immutable TuGraph import package.

    JSON lines are used instead of CSV so an absent optional property (JSON
    ``null``) remains distinguishable from a real empty string.
    """

    ordered_vertices = tuple(sorted(vertices, key=lambda item: (item.label, item.uid)))
    ordered_edges = tuple(sorted(edges, key=lambda item: (item.edge_type, item.edge_uid)))
    validation = validate_graph(ordered_vertices, ordered_edges)
    if not validation.is_valid:
        details = "; ".join(
            f"{issue.code}:{issue.record_id or '-'}:{issue.message}"
            for issue in validation.errors[:20]
        )
        raise TuGraphExportError(
            f"CIR validation failed with {len(validation.errors)} errors: {details}"
        )

    build_ids = {item.build_id for item in ordered_vertices}
    build_ids.update(item.build_id for item in ordered_edges)
    if len(build_ids) != 1:
        raise TuGraphExportError(
            f"TuGraph package must contain exactly one build_id, found {sorted(build_ids)}"
        )
    build_id = next(iter(build_ids))

    root = Path(output_dir)
    try:
        root.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise TuGraphExportError(
            f"Output directory already exists; refusing to overwrite: {root}"
        ) from exc
    incomplete_marker = root / ".incomplete"
    incomplete_marker.write_text(f"build_id={build_id}\n", encoding="utf-8")

    artifacts: list[TuGraphArtifact] = []
    file_configs: list[dict[str, Any]] = []
    vertices_by_uid = {vertex.uid: vertex for vertex in ordered_vertices}

    for label in sorted({record.label for record in ordered_vertices}):
        schema = VERTEX_SCHEMAS[label]
        records = [record for record in ordered_vertices if record.label == label]
        relative_path = f"vertices/{_file_stem(label)}.jsonl"
        columns = list(schema.properties)
        artifacts.append(
            _write_json_lines(
                root,
                relative_path,
                (
                    [_vertex_values(record, schema).get(name) for name in columns]
                    for record in records
                ),
            )
        )
        file_configs.append(
            {
                "columns": columns,
                "format": "JSON",
                "header": 0,
                "label": label,
                "path": relative_path,
            }
        )

    grouped_edges: dict[tuple[str, str, str], list[EdgeRecord]] = {}
    for edge in ordered_edges:
        source = vertices_by_uid[edge.src_uid]
        target = vertices_by_uid[edge.dst_uid]
        grouped_edges.setdefault(
            (edge.edge_type, source.label, target.label), []
        ).append(edge)

    for (edge_type, source_label, target_label), records in sorted(grouped_edges.items()):
        schema = EDGE_SCHEMAS[edge_type]
        property_columns = list(schema.properties)
        columns = ["SRC_ID", *property_columns, "DST_ID"]
        relative_path = (
            f"edges/{_file_stem(edge_type)}__{_file_stem(source_label)}"
            f"__{_file_stem(target_label)}.jsonl"
        )
        artifacts.append(
            _write_json_lines(
                root,
                relative_path,
                (
                    [
                        record.src_uid,
                        *[
                            _edge_values(record).get(name)
                            for name in property_columns
                        ],
                        record.dst_uid,
                    ]
                    for record in records
                ),
            )
        )
        file_configs.append(
            {
                "DST_ID": target_label,
                "SRC_ID": source_label,
                "columns": columns,
                "format": "JSON",
                "header": 0,
                "label": edge_type,
                "path": relative_path,
            }
        )

    config = {
        "files": file_configs,
        "schema": build_tugraph_schema_config(),
    }
    artifacts.append(_write_json_object(root / "import.config.json", config))

    vertex_counts: dict[str, int] = {}
    for record in ordered_vertices:
        vertex_counts[record.label] = vertex_counts.get(record.label, 0) + 1
    edge_counts: dict[str, int] = {}
    endpoint_counts: dict[str, int] = {}
    for record in ordered_edges:
        edge_counts[record.edge_type] = edge_counts.get(record.edge_type, 0) + 1
        source_label = vertices_by_uid[record.src_uid].label
        target_label = vertices_by_uid[record.dst_uid].label
        endpoint_key = f"{record.edge_type}:{source_label}->{target_label}"
        endpoint_counts[endpoint_key] = endpoint_counts.get(endpoint_key, 0) + 1
    preflight_report = {
        "build_id": build_id,
        "edge_count_by_label": dict(sorted(edge_counts.items())),
        "edge_count_by_endpoint_pair": dict(sorted(endpoint_counts.items())),
        "id_codec_version": ID_CODEC_VERSION,
        "source_schema_version": source_schema_version,
        "status": "passed",
        "target": f"TuGraph {TUGRAPH_TARGET_VERSION}",
        "totals": {
            "edge_count": len(ordered_edges),
            "error_count": 0,
            "vertex_count": len(ordered_vertices),
            "warning_count": len(validation.warnings),
        },
        "vertex_count_by_label": dict(sorted(vertex_counts.items())),
        "warnings": [
            {
                "code": issue.code,
                "message": issue.message,
                "record_id": issue.record_id,
            }
            for issue in validation.warnings
        ],
    }
    artifacts.append(
        _write_json_object(root / "validation_report.json", preflight_report)
    )

    manifest = TuGraphExportManifest(
        build_id=build_id,
        artifacts=tuple(artifacts),
        vertex_count=len(ordered_vertices),
        edge_count=len(ordered_edges),
        source_schema_version=source_schema_version,
    )
    _write_json_object(root / "manifest.json", manifest.to_dict())
    incomplete_marker.unlink()
    return manifest
