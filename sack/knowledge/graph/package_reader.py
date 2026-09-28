"""Verified reader for immutable canonical graph packages."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from sack.knowledge.graph.model import EdgeRecord, VertexRecord
from sack.knowledge.graph.schema_registry import SCHEMA_VERSION


class PackageReadError(ValueError):
    """Raised when a canonical package is incomplete or has been modified."""


@dataclass(frozen=True, slots=True)
class CanonicalGraphPackage:
    vertices: tuple[VertexRecord, ...]
    edges: tuple[EdgeRecord, ...]
    manifest: Mapping[str, Any]


_VERTEX_CORE_FIELDS = {"uid", "uri", "label", "build_id", "source_hash"}
_EDGE_CORE_FIELDS = {
    "edge_uid",
    "edge_type",
    "src_uid",
    "dst_uid",
    "build_id",
    "scope_uid",
}


def _load_object(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackageReadError(f"Cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise PackageReadError(f"JSON document must be an object: {path}")
    return value


def _required_string(values: Mapping[str, Any], name: str, path: Path) -> str:
    value = values.get(name)
    if not isinstance(value, str) or not value:
        raise PackageReadError(f"{path}: {name} must be a non-empty string")
    return value


def _read_artifact(
    package_dir: Path,
    artifact: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    relative_path = _required_string(artifact, "relative_path", package_dir / "manifest.json")
    path = package_dir / relative_path
    try:
        resolved_path = path.resolve(strict=True)
        resolved_root = package_dir.resolve(strict=True)
    except OSError as exc:
        raise PackageReadError(f"Missing package artifact {path}: {exc}") from exc
    if resolved_root not in resolved_path.parents:
        raise PackageReadError(f"Artifact escapes package directory: {relative_path}")

    payload = resolved_path.read_bytes()
    expected_size = artifact.get("byte_count")
    if expected_size != len(payload):
        raise PackageReadError(
            f"Artifact byte count mismatch for {relative_path}: "
            f"expected {expected_size}, found {len(payload)}"
        )
    expected_digest = _required_string(artifact, "sha256", package_dir / "manifest.json")
    actual_digest = hashlib.sha256(payload).hexdigest()
    if actual_digest != expected_digest:
        raise PackageReadError(f"Artifact digest mismatch for {relative_path}")

    records: list[Mapping[str, Any]] = []
    for line_number, raw_line in enumerate(payload.splitlines(), start=1):
        try:
            value = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise PackageReadError(
                f"Invalid JSON in {relative_path}:{line_number}: {exc}"
            ) from exc
        if not isinstance(value, Mapping):
            raise PackageReadError(
                f"Record must be an object in {relative_path}:{line_number}"
            )
        records.append(value)
    if artifact.get("row_count") != len(records):
        raise PackageReadError(
            f"Artifact row count mismatch for {relative_path}: "
            f"expected {artifact.get('row_count')}, found {len(records)}"
        )
    return records


def read_canonical_package(package_dir: str | Path) -> CanonicalGraphPackage:
    """Read a CIR package only after verifying its marker, schema, and hashes."""

    root = Path(package_dir)
    if not root.is_dir():
        raise PackageReadError(f"Canonical package directory does not exist: {root}")
    if (root / ".incomplete").exists():
        raise PackageReadError(f"Canonical package is incomplete: {root}")
    manifest = _load_object(root / "manifest.json")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise PackageReadError(
            "Canonical package schema version mismatch: "
            f"expected {SCHEMA_VERSION}, found {manifest.get('schema_version')!r}"
        )

    raw_artifacts = manifest.get("artifacts")
    if not isinstance(raw_artifacts, list):
        raise PackageReadError("manifest.artifacts must be an array")

    vertices: list[VertexRecord] = []
    edges: list[EdgeRecord] = []
    seen_paths: set[str] = set()
    for raw_artifact in raw_artifacts:
        if not isinstance(raw_artifact, Mapping):
            raise PackageReadError("Each manifest artifact must be an object")
        relative_path = _required_string(raw_artifact, "relative_path", root / "manifest.json")
        if relative_path in seen_paths:
            raise PackageReadError(f"Duplicate artifact path in manifest: {relative_path}")
        seen_paths.add(relative_path)
        kind = raw_artifact.get("record_kind")
        label = _required_string(raw_artifact, "label", root / "manifest.json")
        records = _read_artifact(root, raw_artifact)

        for values in records:
            try:
                if kind == "vertex":
                    if values.get("label") != label:
                        raise PackageReadError(
                            f"Artifact {relative_path} declares {label}, "
                            f"but contains {values.get('label')!r}"
                        )
                    vertices.append(
                        VertexRecord(
                            uid=_required_string(values, "uid", root / relative_path),
                            uri=_required_string(values, "uri", root / relative_path),
                            label=label,
                            properties={
                                key: value
                                for key, value in values.items()
                                if key not in _VERTEX_CORE_FIELDS
                            },
                            build_id=_required_string(values, "build_id", root / relative_path),
                            source_hash=values.get("source_hash"),
                        )
                    )
                elif kind == "edge":
                    if values.get("edge_type") != label:
                        raise PackageReadError(
                            f"Artifact {relative_path} declares {label}, "
                            f"but contains {values.get('edge_type')!r}"
                        )
                    edges.append(
                        EdgeRecord(
                            edge_uid=_required_string(values, "edge_uid", root / relative_path),
                            edge_type=label,
                            src_uid=_required_string(values, "src_uid", root / relative_path),
                            dst_uid=_required_string(values, "dst_uid", root / relative_path),
                            properties={
                                key: value
                                for key, value in values.items()
                                if key not in _EDGE_CORE_FIELDS
                            },
                            build_id=_required_string(values, "build_id", root / relative_path),
                            scope_uid=values.get("scope_uid"),
                        )
                    )
                else:
                    raise PackageReadError(
                        f"Unsupported record_kind {kind!r} for {relative_path}"
                    )
            except (TypeError, ValueError) as exc:
                if isinstance(exc, PackageReadError):
                    raise
                raise PackageReadError(f"Invalid record in {relative_path}: {exc}") from exc

    return CanonicalGraphPackage(
        vertices=tuple(sorted(vertices, key=lambda item: (item.label, item.uid))),
        edges=tuple(sorted(edges, key=lambda item: (item.edge_type, item.edge_uid))),
        manifest=manifest,
    )
