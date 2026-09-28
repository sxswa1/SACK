"""Canonical intermediate records for storage-neutral graph construction."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from sack.knowledge.graph.id_codec import (
    edge_uid as make_edge_uid,
    is_uid,
    normalize_uri,
    vertex_uid,
)


_VERTEX_LABEL = re.compile(r"^[A-Z][A-Za-z0-9_]*$")
_EDGE_TYPE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_PROPERTY_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_VERTEX_RESERVED_PROPERTIES = {"uid", "uri", "label", "build_id", "source_hash"}
_EDGE_RESERVED_PROPERTIES = {
    "edge_uid",
    "edge_type",
    "src_uid",
    "dst_uid",
    "scope_uid",
    "build_id",
}


class RecordValidationError(ValueError):
    """Raised when a CIR record violates a storage-independent invariant."""


def _validate_build_id(build_id: str) -> None:
    if not isinstance(build_id, str) or not build_id.strip():
        raise RecordValidationError("build_id must be a non-empty string")
    if build_id != build_id.strip():
        raise RecordValidationError("build_id must not have surrounding whitespace")


def _validate_source_hash(source_hash: str | None) -> None:
    if source_hash is not None and not is_uid(source_hash):
        raise RecordValidationError("source_hash must be a SHA-256 hexadecimal digest")


def _normalize_json_value(value: Any, path: str) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        raise RecordValidationError(f"{path} must not contain NaN or infinity")
    if isinstance(value, Mapping):
        normalized = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise RecordValidationError(f"{path} object keys must be strings")
            normalized[key] = _normalize_json_value(item, f"{path}.{key}")
        return normalized
    if isinstance(value, (list, tuple)):
        return [
            _normalize_json_value(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise RecordValidationError(
        f"{path} contains unsupported type {type(value).__name__}"
    )


def _normalize_properties(
    properties: Mapping[str, Any], reserved: set[str]
) -> dict[str, Any]:
    if not isinstance(properties, Mapping):
        raise RecordValidationError("properties must be a mapping")

    normalized: dict[str, Any] = {}
    for key, value in properties.items():
        if not isinstance(key, str) or _PROPERTY_NAME.fullmatch(key) is None:
            raise RecordValidationError(
                f"Invalid property name {key!r}; use letters, numbers, and underscores"
            )
        if key in reserved:
            raise RecordValidationError(f"Property {key!r} is reserved by the CIR model")
        normalized[key] = _normalize_json_value(value, f"properties.{key}")

    # This is also a guard against future changes to the normalizer.
    json.dumps(normalized, allow_nan=False, ensure_ascii=False, sort_keys=True)
    return normalized


@dataclass(frozen=True, slots=True)
class VertexRecord:
    """A vertex independent of RDF and TuGraph serialization details."""

    uid: str
    uri: str
    label: str
    properties: Mapping[str, Any]
    build_id: str
    source_hash: str | None = None

    def __post_init__(self) -> None:
        canonical_uri = normalize_uri(self.uri)
        expected_uid = vertex_uid(canonical_uri)
        if self.uid != expected_uid:
            raise RecordValidationError(
                f"Vertex uid does not match canonical URI; expected {expected_uid}"
            )
        if not isinstance(self.label, str) or _VERTEX_LABEL.fullmatch(self.label) is None:
            raise RecordValidationError(
                "Vertex label must be a concrete PascalCase identifier"
            )
        _validate_build_id(self.build_id)
        _validate_source_hash(self.source_hash)

        object.__setattr__(self, "uri", canonical_uri)
        object.__setattr__(
            self,
            "properties",
            _normalize_properties(self.properties, _VERTEX_RESERVED_PROPERTIES),
        )

    @classmethod
    def from_uri(
        cls,
        *,
        uri: str,
        label: str,
        properties: Mapping[str, Any],
        build_id: str,
        source_hash: str | None = None,
    ) -> "VertexRecord":
        canonical_uri = normalize_uri(uri)
        return cls(
            uid=vertex_uid(canonical_uri),
            uri=canonical_uri,
            label=label,
            properties=properties,
            build_id=build_id,
            source_hash=source_hash,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "build_id": self.build_id,
            "label": self.label,
            "uid": self.uid,
            "uri": self.uri,
        }
        if self.source_hash is not None:
            result["source_hash"] = self.source_hash
        result.update(self.properties)
        return result


@dataclass(frozen=True, slots=True)
class EdgeRecord:
    """A directed edge with optional properties and Pipeline scope."""

    edge_uid: str
    edge_type: str
    src_uid: str
    dst_uid: str
    properties: Mapping[str, Any]
    build_id: str
    scope_uid: str | None = None

    def __post_init__(self) -> None:
        if not is_uid(self.edge_uid):
            raise RecordValidationError("edge_uid must be a SHA-256 hexadecimal digest")
        if not isinstance(self.edge_type, str) or _EDGE_TYPE.fullmatch(self.edge_type) is None:
            raise RecordValidationError("edge_type must use upper snake case")
        if not is_uid(self.src_uid) or not is_uid(self.dst_uid):
            raise RecordValidationError("Edge endpoints must be canonical vertex UIDs")
        if self.scope_uid is not None and not is_uid(self.scope_uid):
            raise RecordValidationError("scope_uid must be a canonical vertex UID")
        _validate_build_id(self.build_id)
        object.__setattr__(
            self,
            "properties",
            _normalize_properties(self.properties, _EDGE_RESERVED_PROPERTIES),
        )

    @classmethod
    def from_endpoints(
        cls,
        *,
        edge_type: str,
        src_uid: str,
        dst_uid: str,
        properties: Mapping[str, Any],
        build_id: str,
        scope_uid: str | None = None,
        discriminator: Any = None,
    ) -> "EdgeRecord":
        identity = {
            "discriminator": discriminator,
            "scope_uid": scope_uid,
        }
        return cls(
            edge_uid=make_edge_uid(edge_type, src_uid, dst_uid, identity),
            edge_type=edge_type,
            src_uid=src_uid,
            dst_uid=dst_uid,
            properties=properties,
            build_id=build_id,
            scope_uid=scope_uid,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "build_id": self.build_id,
            "dst_uid": self.dst_uid,
            "edge_type": self.edge_type,
            "edge_uid": self.edge_uid,
            "src_uid": self.src_uid,
        }
        if self.scope_uid is not None:
            result["scope_uid"] = self.scope_uid
        result.update(self.properties)
        return result


def record_json(record: VertexRecord | EdgeRecord) -> str:
    """Serialize a CIR record deterministically for JSONL output and hashing."""

    return json.dumps(
        record.to_dict(),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
