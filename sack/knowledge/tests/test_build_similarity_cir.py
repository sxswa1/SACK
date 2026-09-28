import pytest

from sack.knowledge.graph.model import VertexRecord
from sack.knowledge.graph.package_reader import read_canonical_package
from sack.knowledge.graph.package_writer import CanonicalPackageWriter
from sack.knowledge.migration.build_similarity_cir import (
    SimilarityPackageBuildError,
    build_similarity_package,
)


BUILD_ID = "similarity-test"
FIRST_URI = "http://sack.local/resource/kaggle/one/train.csv/a"
SECOND_URI = "http://sack.local/resource/kaggle/two/train.csv/b"
PREDICATE = "http://sack.local/ontology/data/hasContentSimilarity"
CERTAINTY = "http://sack.local/ontology/data/withCertainty"


def _profile_package(tmp_path):
    output = tmp_path / "profile-package"
    writer = CanonicalPackageWriter(output, build_id=BUILD_ID)
    for uri in (FIRST_URI, SECOND_URI):
        writer.write_vertex(
            VertexRecord.from_uri(
                uri=uri,
                label="Column",
                properties={"name": uri.rsplit("/", 1)[-1]},
                build_id=BUILD_ID,
            )
        )
    writer.finalize()
    return output


def _assertion(source, target, score="0.875"):
    return f"<<<{source}> <{PREDICATE}> <{target}>>> <{CERTAINTY}> {score}.\n"


def test_similarity_ttl_preserves_directed_pairs_and_certainty(tmp_path):
    profile = _profile_package(tmp_path)
    ttl = tmp_path / "global.ttl"
    ttl.write_text(
        "<http://sack.local/resource/x> <http://sack.local/ontology/name> \"x\".\n"
        + _assertion(FIRST_URI, SECOND_URI)
        + _assertion(SECOND_URI, FIRST_URI),
        encoding="utf-8",
    )

    manifest = build_similarity_package(
        global_schema_ttl=ttl,
        profile_package=profile,
        output_dir=tmp_path / "similarity-package",
    )
    package = read_canonical_package(tmp_path / "similarity-package")

    assert manifest.to_dict()["totals"]["edge_count"] == 2
    assert manifest.to_dict()["totals"]["vertex_count"] == 2
    assert {edge.properties["certainty"] for edge in package.edges} == {0.875}
    assert package.edges[0].src_uid == package.edges[1].dst_uid


def test_similarity_ttl_rejects_missing_reverse_or_unparsed_assertion(tmp_path):
    profile = _profile_package(tmp_path)
    ttl = tmp_path / "global.ttl"
    ttl.write_text(_assertion(FIRST_URI, SECOND_URI), encoding="utf-8")

    with pytest.raises(SimilarityPackageBuildError, match="missing_reverse_similarity"):
        build_similarity_package(
            global_schema_ttl=ttl,
            profile_package=profile,
            output_dir=tmp_path / "similarity-package",
        )

    ttl.write_text("<<bad assertion>>\n", encoding="utf-8")
    with pytest.raises(SimilarityPackageBuildError, match="Unsupported RDF-star"):
        build_similarity_package(
            global_schema_ttl=ttl,
            profile_package=profile,
            output_dir=tmp_path / "similarity-package",
        )


def test_similarity_ttl_requires_explicit_empty_decision(tmp_path):
    profile = _profile_package(tmp_path)
    ttl = tmp_path / "global.ttl"
    ttl.write_text("", encoding="utf-8")

    with pytest.raises(SimilarityPackageBuildError, match="no RDF-star"):
        build_similarity_package(
            global_schema_ttl=ttl,
            profile_package=profile,
            output_dir=tmp_path / "similarity-package",
        )

    manifest = build_similarity_package(
        global_schema_ttl=ttl,
        profile_package=profile,
        output_dir=tmp_path / "empty-similarity-package",
        allow_empty=True,
    )
    assert manifest.to_dict()["totals"]["edge_count"] == 0
