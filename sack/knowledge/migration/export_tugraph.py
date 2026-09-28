"""Convert a verified canonical package into a TuGraph import package.

Example:

    python -m sack.knowledge.migration.export_tugraph \
        --canonical-package storage/canonical/build-001/full \
        --output-dir storage/tugraph/build-001
"""

from __future__ import annotations

import argparse
from pathlib import Path

from sack.knowledge.graph.package_reader import read_canonical_package
from sack.knowledge.graph.sinks.tugraph import export_tugraph_package


class IncompleteCanonicalGraphError(ValueError):
    """Raised when a production export omits a required CIR source."""


def export_canonical_package(
    *,
    canonical_package: str | Path,
    output_dir: str | Path,
    allow_partial: bool = False,
):
    package = read_canonical_package(canonical_package)
    if not allow_partial:
        metadata = package.manifest.get("metadata", {})
        scopes = metadata.get("input_package_scopes", [])
        required = {"profile-structure", "column-similarity", "pipeline"}
        if (
            metadata.get("package_scope") != "full"
            or not isinstance(scopes, list)
            or len(scopes) != 3
            or set(scopes) != required
        ):
            raise IncompleteCanonicalGraphError(
                "Production TuGraph export requires a full CIR package merged "
                "from profile-structure, column-similarity, and pipeline; "
                "use --allow-partial only for explicit test fixtures"
            )
    return export_tugraph_package(
        package.vertices,
        package.edges,
        output_dir,
        source_schema_version=str(package.manifest["schema_version"]),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a verified canonical graph package for TuGraph 4.5.2."
    )
    parser.add_argument("--canonical-package", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--allow-partial", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    manifest = export_canonical_package(
        canonical_package=args.canonical_package,
        output_dir=args.output_dir,
        allow_partial=args.allow_partial,
    )
    print(
        "TuGraph import package built: "
        f"vertices={manifest.vertex_count}, edges={manifest.edge_count}, "
        f"output={args.output_dir}"
    )


if __name__ == "__main__":
    main()
