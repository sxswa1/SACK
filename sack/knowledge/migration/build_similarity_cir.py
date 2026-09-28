"""Preserve RDF-star column similarities from the existing global-schema TTL."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

from sack.knowledge.graph.id_codec import vertex_uid
from sack.knowledge.graph.manifest import GraphPackageManifest
from sack.knowledge.graph.model import EdgeRecord, VertexRecord
from sack.knowledge.graph.package_reader import read_canonical_package
from sack.knowledge.graph.package_writer import CanonicalPackageWriter
from sack.knowledge.graph.validation import validate_graph


class SimilarityPackageBuildError(RuntimeError):
    """Raised when a source RDF-star assertion cannot be preserved exactly."""


_ASSERTION = re.compile(
    r"^<<(?P<source><[^<>\s]+>) "
    r"(?P<predicate><http://sack\.local/ontology/data/has(?:Content|Label)Similarity>) "
    r"(?P<target><[^<>\s]+>)>> "
    r"<http://sack\.local/ontology/data/withCertainty> "
    r"(?P<certainty>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\.$"
)
_RELATION_TYPES = {
    "http://sack.local/ontology/data/hasContentSimilarity": "HAS_CONTENT_SIMILARITY",
    "http://sack.local/ontology/data/hasLabelSimilarity": "HAS_LABEL_SIMILARITY",
}


def build_similarity_package(
    *,
    global_schema_ttl: str | Path,
    profile_package: str | Path,
    output_dir: str | Path,
    generated_at: str | None = None,
    allow_empty: bool = False,
) -> GraphPackageManifest:
    """Extract only the existing RDF-star edges; never recompute their scores."""

    source_path = Path(global_schema_ttl)
    if not source_path.is_file():
        raise SimilarityPackageBuildError(
            f"Global-schema TTL file does not exist: {source_path}"
        )
    package = read_canonical_package(profile_package)
    build_id = str(package.manifest["build_id"])
    columns = {
        vertex.uid: vertex
        for vertex in package.vertices
        if vertex.label == "Column"
    }
    if not columns:
        raise SimilarityPackageBuildError("Profile package has no Column vertices")

    edges: dict[str, EdgeRecord] = {}
    source_hash = hashlib.sha256()
    with source_path.open("rb") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            source_hash.update(raw_line)
            try:
                line = raw_line.decode("utf-8").strip()
            except UnicodeDecodeError as exc:
                raise SimilarityPackageBuildError(
                    f"Invalid UTF-8 in {source_path}:{line_number}"
                ) from exc
            if not line.startswith("<<"):
                continue
            match = _ASSERTION.fullmatch(line)
            if match is None:
                raise SimilarityPackageBuildError(
                    f"Unsupported RDF-star assertion at {source_path}:{line_number}"
                )
            source_uri = match.group("source")[1:-1]
            target_uri = match.group("target")[1:-1]
            source_uid = vertex_uid(source_uri)
            target_uid = vertex_uid(target_uri)
            if source_uid not in columns or target_uid not in columns:
                raise SimilarityPackageBuildError(
                    f"RDF-star assertion references an unknown Column at "
                    f"{source_path}:{line_number}"
                )
            certainty = float(match.group("certainty"))
            edge = EdgeRecord.from_endpoints(
                edge_type=_RELATION_TYPES[match.group("predicate")[1:-1]],
                src_uid=source_uid,
                dst_uid=target_uid,
                properties={"certainty": certainty},
                build_id=build_id,
            )
            previous = edges.get(edge.edge_uid)
            if previous is not None and previous != edge:
                raise SimilarityPackageBuildError(
                    f"Conflicting RDF-star certainty at {source_path}:{line_number}"
                )
            edges[edge.edge_uid] = edge

    if not edges and not allow_empty:
        raise SimilarityPackageBuildError(
            "Global-schema TTL contains no RDF-star similarity assertions; "
            "pass --allow-empty only after confirming that the source build omitted them"
        )

    referenced_uids = {uid for edge in edges.values() for uid in (edge.src_uid, edge.dst_uid)}
    sparse_columns = tuple(
        VertexRecord.from_uri(
            uri=columns[uid].uri,
            label="Column",
            properties={},
            build_id=build_id,
        )
        for uid in sorted(referenced_uids)
    )
    validation = validate_graph(sparse_columns, edges.values())
    if not validation.is_valid:
        details = "; ".join(
            f"{issue.code}:{issue.record_id or '-'}:{issue.message}"
            for issue in validation.errors[:20]
        )
        raise SimilarityPackageBuildError(
            f"RDF-star similarity validation failed with "
            f"{len(validation.errors)} errors: {details}"
        )

    writer = CanonicalPackageWriter(
        output_dir,
        build_id=build_id,
        generated_at=generated_at,
        metadata={
            "includes_similarity_edges": True,
            "package_scope": "column-similarity",
            "source_global_schema_ttl": str(source_path),
            "source_global_schema_ttl_sha256": source_hash.hexdigest(),
            "validation_error_count": 0,
            "validation_warning_count": len(validation.warnings),
        },
    )
    for vertex in sparse_columns:
        writer.write_vertex(vertex)
    for edge in sorted(edges.values(), key=lambda item: (item.edge_type, item.edge_uid)):
        writer.write_edge(edge)
    return writer.finalize()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract existing RDF-star similarities into a verified CIR package."
    )
    parser.add_argument("--global-schema-ttl", required=True, type=Path)
    parser.add_argument("--profile-package", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--allow-empty", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    manifest = build_similarity_package(
        global_schema_ttl=args.global_schema_ttl,
        profile_package=args.profile_package,
        output_dir=args.output_dir,
        allow_empty=args.allow_empty,
    )
    totals = manifest.to_dict()["totals"]
    print(
        "Canonical similarity package built: "
        f"vertices={totals['vertex_count']}, edges={totals['edge_count']}, "
        f"output={args.output_dir}"
    )


if __name__ == "__main__":
    main()
