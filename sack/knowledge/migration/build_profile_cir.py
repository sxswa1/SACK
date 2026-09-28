"""Build the profile-backed portion of a canonical graph package.

This command intentionally does not replace ``build_knowledge.py`` and does not
load GraphDB or TuGraph.  It exports Source, Dataset, Table, Column, and EDA
records.  Similarity edges and Pipeline records are added by later migration
stages and are explicitly marked absent in the package manifest for now.

Example:

    python -m sack.knowledge.migration.build_profile_cir \
        --profiles-dir storage/profiles/kaggle_profiles \
        --output-dir storage/canonical/build-001/profile \
        --build-id build-001
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from sack.knowledge.graph.builders.global_schema import build_global_schema_records
from sack.knowledge.graph.manifest import GraphPackageManifest
from sack.knowledge.graph.package_writer import CanonicalPackageWriter
from sack.knowledge.graph.validation import validate_graph
from sack.knowledge.kg_governor.data_profiling.model.column_profile import ColumnProfile
from sack.knowledge.kg_governor.data_profiling.model.competition_profile import CompetitionProfile
from sack.knowledge.kg_governor.data_profiling.model.edainsight_profile import EDAInsightProfile


class ProfilePackageBuildError(RuntimeError):
    """Raised when persisted Profiles cannot produce a valid CIR package."""


def load_profiles(
    profiles_dir: str | Path,
) -> tuple[list[ColumnProfile], dict[str, CompetitionProfile], dict[str, list[EDAInsightProfile]]]:
    base_dir = Path(profiles_dir)
    if not base_dir.is_dir():
        raise ProfilePackageBuildError(f"Profiles directory does not exist: {base_dir}")

    competition_dir = base_dir / "competition_profiles"
    eda_dir = base_dir / "eda_insight_profiles"
    excluded = {competition_dir, eda_dir}

    column_profiles: list[ColumnProfile] = []
    for path in sorted(base_dir.glob("*/*.json")):
        if path.parent in excluded:
            continue
        column_profiles.append(ColumnProfile.load_profile(path))
    if not column_profiles:
        raise ProfilePackageBuildError(f"No column profiles found under {base_dir}")

    competition_profiles: dict[str, CompetitionProfile] = {}
    if competition_dir.is_dir():
        for path in sorted(competition_dir.glob("*.json")):
            profile = CompetitionProfile.load_profile(path)
            competition_id = profile.get_competition_id()
            previous = competition_profiles.get(competition_id)
            if previous is not None and previous.to_dict() != profile.to_dict():
                raise ProfilePackageBuildError(
                    f"Conflicting competition profiles for {competition_id}"
                )
            competition_profiles[competition_id] = profile

    eda_profiles: dict[str, list[EDAInsightProfile]] = {}
    eda_ids: dict[str, dict[str, Any]] = {}
    if eda_dir.is_dir():
        for path in sorted(eda_dir.glob("*.json")):
            profile = EDAInsightProfile.load_profile(path)
            payload = profile.to_dict()
            eda_id = profile.get_eda_id()
            previous = eda_ids.get(eda_id)
            if previous is not None and previous != payload:
                raise ProfilePackageBuildError(f"Conflicting EDA profiles for {eda_id}")
            eda_ids[eda_id] = payload
            eda_profiles.setdefault(profile.get_competition_id(), []).append(profile)

    return column_profiles, competition_profiles, eda_profiles


def build_profile_package(
    *,
    profiles_dir: str | Path,
    output_dir: str | Path,
    build_id: str,
    generated_at: str | None = None,
) -> GraphPackageManifest:
    columns, competitions, eda_profiles = load_profiles(profiles_dir)
    records = build_global_schema_records(
        columns,
        build_id=build_id,
        competition_profiles=competitions,
        eda_profiles=eda_profiles,
    )
    validation = validate_graph(records.vertices, records.edges)
    if not validation.is_valid:
        details = "; ".join(
            f"{issue.code}:{issue.record_id or '-'}:{issue.message}"
            for issue in validation.errors[:20]
        )
        raise ProfilePackageBuildError(
            f"Canonical profile graph validation failed with {len(validation.errors)} errors: {details}"
        )

    metadata = {
        "competition_profile_count": len(competitions),
        "column_profile_count": len(columns),
        "eda_profile_count": sum(len(items) for items in eda_profiles.values()),
        "includes_pipeline_graph": False,
        "includes_similarity_edges": False,
        "package_scope": "profile-structure",
        "source_profiles_dir": str(Path(profiles_dir)),
        "validation_error_count": 0,
        "validation_warning_count": len(validation.warnings),
    }
    writer = CanonicalPackageWriter(
        output_dir,
        build_id=build_id,
        generated_at=generated_at,
        metadata=metadata,
    )
    for vertex in records.vertices:
        writer.write_vertex(vertex)
    for edge in records.edges:
        writer.write_edge(edge)
    return writer.finalize()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export the profile-backed SACK graph as a canonical JSONL package."
    )
    parser.add_argument("--profiles-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--build-id", required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    manifest = build_profile_package(
        profiles_dir=args.profiles_dir,
        output_dir=args.output_dir,
        build_id=args.build_id,
    )
    totals = manifest.to_dict()["totals"]
    print(
        "Canonical profile package built: "
        f"vertices={totals['vertex_count']}, edges={totals['edge_count']}, "
        f"output={args.output_dir}"
    )


if __name__ == "__main__":
    main()
