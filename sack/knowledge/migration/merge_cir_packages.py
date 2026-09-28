"""Merge verified partial CIR packages into one validated full package.

This is the boundary between independently replayable builders (for example,
Profile and Pipeline) and storage-specific sinks.  Shared sparse references are
merged deterministically; contradictory properties fail closed.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from sack.knowledge.graph.manifest import GraphPackageManifest
from sack.knowledge.graph.merge import RecordMergeError, merge_graph_records
from sack.knowledge.graph.package_reader import read_canonical_package
from sack.knowledge.graph.package_writer import CanonicalPackageWriter
from sack.knowledge.graph.validation import validate_graph


class PackageMergeError(RuntimeError):
    """Raised when partial packages cannot form one consistent graph."""


def merge_canonical_packages(
    *,
    input_dirs: Sequence[str | Path],
    output_dir: str | Path,
    generated_at: str | None = None,
) -> GraphPackageManifest:
    if len(input_dirs) < 2:
        raise PackageMergeError("At least two canonical packages are required")
    packages = [read_canonical_package(path) for path in input_dirs]
    build_ids = {str(package.manifest.get("build_id")) for package in packages}
    if len(build_ids) != 1:
        raise PackageMergeError(
            f"All canonical packages must share one build_id, found {sorted(build_ids)}"
        )
    build_id = next(iter(build_ids))
    input_scopes = [
        package.manifest.get("metadata", {}).get("package_scope")
        for package in packages
    ]

    try:
        merged = merge_graph_records(
            vertex_groups=(package.vertices for package in packages),
            edge_groups=(package.edges for package in packages),
        )
    except RecordMergeError as exc:
        raise PackageMergeError(f"Canonical package conflict: {exc}") from exc
    validation = validate_graph(merged.vertices, merged.edges)
    if not validation.is_valid:
        details = "; ".join(
            f"{issue.code}:{issue.record_id or '-'}:{issue.message}"
            for issue in validation.errors[:20]
        )
        raise PackageMergeError(
            f"Merged canonical graph has {len(validation.errors)} errors: {details}"
        )

    writer = CanonicalPackageWriter(
        output_dir,
        build_id=build_id,
        generated_at=generated_at,
        metadata={
            "input_packages": [str(Path(path)) for path in input_dirs],
            "input_package_scopes": input_scopes,
            "package_scope": "full",
            "validation_error_count": 0,
            "validation_warning_count": len(validation.warnings),
        },
    )
    for record in merged.vertices:
        writer.write_vertex(record)
    for record in merged.edges:
        writer.write_edge(record)
    return writer.finalize()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge two or more verified canonical graph packages."
    )
    parser.add_argument("--input-dir", action="append", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    manifest = merge_canonical_packages(
        input_dirs=args.input_dir,
        output_dir=args.output_dir,
    )
    totals = manifest.to_dict()["totals"]
    print(
        "Full canonical package built: "
        f"vertices={totals['vertex_count']}, edges={totals['edge_count']}, "
        f"output={args.output_dir}"
    )


if __name__ == "__main__":
    main()
