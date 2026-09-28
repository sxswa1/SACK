"""Streaming JSONL writer for canonical graph packages.

Records must be grouped by label and sorted by their stable identifier.  This
keeps output deterministic without loading the complete knowledge graph into
memory.  The writer rejects out-of-order or duplicate records rather than
silently producing a non-reproducible package.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Mapping

from sack.knowledge.graph.manifest import ArtifactManifest, GraphPackageManifest
from sack.knowledge.graph.model import EdgeRecord, VertexRecord, record_json
from sack.knowledge.graph.schema_registry import get_edge_schema, get_vertex_schema


class PackageWriteError(ValueError):
    """Raised when a package cannot be written without losing determinism."""


def _file_stem(label: str) -> str:
    first_pass = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", label)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", first_pass).lower()


def _json_safe_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    try:
        serialized = json.dumps(
            dict(values),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise PackageWriteError(f"Package metadata is not valid JSON: {exc}") from exc
    return json.loads(serialized)


@dataclass(slots=True)
class _ArtifactWriter:
    path: Path
    relative_path: str
    record_kind: str
    label: str
    handle: BinaryIO
    digest: Any = field(default_factory=hashlib.sha256)
    row_count: int = 0
    byte_count: int = 0
    last_record_id: str | None = None

    def write(self, record_id: str, payload: bytes) -> None:
        if self.last_record_id is not None and record_id <= self.last_record_id:
            relation = "duplicate" if record_id == self.last_record_id else "out-of-order"
            raise PackageWriteError(
                f"{self.label} contains a {relation} record id {record_id}; "
                "records must be strictly sorted"
            )
        self.handle.write(payload)
        self.digest.update(payload)
        self.row_count += 1
        self.byte_count += len(payload)
        self.last_record_id = record_id

    def close(self) -> ArtifactManifest:
        self.handle.flush()
        self.handle.close()
        return ArtifactManifest(
            relative_path=self.relative_path,
            record_kind=self.record_kind,
            label=self.label,
            sha256=self.digest.hexdigest(),
            row_count=self.row_count,
            byte_count=self.byte_count,
        )


class CanonicalPackageWriter:
    """Write a new immutable CIR package and finalize it with a manifest."""

    def __init__(
        self,
        output_dir: str | Path,
        *,
        build_id: str,
        metadata: Mapping[str, Any] | None = None,
        generated_at: str | None = None,
    ) -> None:
        if not isinstance(build_id, str) or not build_id.strip():
            raise PackageWriteError("build_id must be a non-empty string")
        if build_id != build_id.strip():
            raise PackageWriteError("build_id must not have surrounding whitespace")

        self.output_dir = Path(output_dir)
        self.build_id = build_id
        self.metadata = _json_safe_mapping(metadata or {})
        self.generated_at = generated_at or datetime.now(timezone.utc).isoformat()
        self._writers: dict[tuple[str, str], _ArtifactWriter] = {}
        self._finalized = False

        try:
            self.output_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise PackageWriteError(
                f"Output directory already exists; refusing to overwrite: {self.output_dir}"
            ) from exc
        (self.output_dir / "vertices").mkdir()
        (self.output_dir / "edges").mkdir()
        self._incomplete_marker = self.output_dir / ".incomplete"
        self._incomplete_marker.write_text(
            f"build_id={self.build_id}\n", encoding="utf-8"
        )

    def __enter__(self) -> "CanonicalPackageWriter":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if exc_type is None:
            self.finalize()
        else:
            self._close_without_manifest()

    def _get_writer(self, record_kind: str, label: str) -> _ArtifactWriter:
        key = (record_kind, label)
        existing = self._writers.get(key)
        if existing is not None:
            return existing

        directory = "vertices" if record_kind == "vertex" else "edges"
        relative_path = f"{directory}/{_file_stem(label)}.jsonl"
        path = self.output_dir / relative_path
        writer = _ArtifactWriter(
            path=path,
            relative_path=relative_path,
            record_kind=record_kind,
            label=label,
            handle=path.open("wb"),
        )
        self._writers[key] = writer
        return writer

    def _ensure_open(self) -> None:
        if self._finalized:
            raise PackageWriteError("Package has already been finalized")

    def write_vertex(self, record: VertexRecord) -> None:
        self._ensure_open()
        if record.build_id != self.build_id:
            raise PackageWriteError(
                f"Vertex build_id {record.build_id!r} does not match package {self.build_id!r}"
            )
        get_vertex_schema(record.label)
        payload = f"{record_json(record)}\n".encode("utf-8")
        self._get_writer("vertex", record.label).write(record.uid, payload)

    def write_edge(self, record: EdgeRecord) -> None:
        self._ensure_open()
        if record.build_id != self.build_id:
            raise PackageWriteError(
                f"Edge build_id {record.build_id!r} does not match package {self.build_id!r}"
            )
        get_edge_schema(record.edge_type)
        payload = f"{record_json(record)}\n".encode("utf-8")
        self._get_writer("edge", record.edge_type).write(record.edge_uid, payload)

    def _close_without_manifest(self) -> None:
        for writer in self._writers.values():
            if not writer.handle.closed:
                writer.handle.close()

    def finalize(self) -> GraphPackageManifest:
        self._ensure_open()
        artifacts = [writer.close() for writer in self._writers.values()]
        manifest = GraphPackageManifest(
            build_id=self.build_id,
            generated_at=self.generated_at,
            artifacts=artifacts,
            metadata=self.metadata,
        )
        manifest_payload = json.dumps(
            manifest.to_dict(),
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
        temporary_manifest = self.output_dir / "manifest.json.partial"
        temporary_manifest.write_text(manifest_payload, encoding="utf-8")
        temporary_manifest.replace(self.output_dir / "manifest.json")
        self._incomplete_marker.unlink()
        self._finalized = True
        return manifest
