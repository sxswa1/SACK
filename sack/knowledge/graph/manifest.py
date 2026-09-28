"""Manifest models for reproducible canonical graph packages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from sack.knowledge.graph.schema_registry import SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class ArtifactManifest:
    relative_path: str
    record_kind: str
    label: str
    sha256: str
    row_count: int
    byte_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "byte_count": self.byte_count,
            "label": self.label,
            "record_kind": self.record_kind,
            "relative_path": self.relative_path,
            "row_count": self.row_count,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class GraphPackageManifest:
    build_id: str
    generated_at: str
    artifacts: Sequence[ArtifactManifest]
    metadata: Mapping[str, Any]
    schema_version: str = SCHEMA_VERSION
    manifest_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        ordered_artifacts = sorted(self.artifacts, key=lambda item: item.relative_path)
        return {
            "artifacts": [artifact.to_dict() for artifact in ordered_artifacts],
            "build_id": self.build_id,
            "generated_at": self.generated_at,
            "manifest_version": self.manifest_version,
            "metadata": dict(self.metadata),
            "schema_version": self.schema_version,
            "totals": {
                "byte_count": sum(item.byte_count for item in ordered_artifacts),
                "edge_count": sum(
                    item.row_count
                    for item in ordered_artifacts
                    if item.record_kind == "edge"
                ),
                "vertex_count": sum(
                    item.row_count
                    for item in ordered_artifacts
                    if item.record_kind == "vertex"
                ),
            },
        }
