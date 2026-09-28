import hashlib

import pytest

from sack.knowledge.graph.id_codec import (
    IdentifierError,
    edge_uid,
    normalize_uri,
    resource_id_to_uri,
    uri_to_resource_id,
    vertex_uid,
)


def test_vertex_uid_is_sha256_of_canonical_existing_uri():
    uri = "HTTP://SACK.LOCAL/resource/kaggle/playground-series-s3e23"
    canonical = "http://sack.local/resource/kaggle/playground-series-s3e23"

    assert normalize_uri(uri) == canonical
    assert vertex_uid(uri) == hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_normalize_uri_preserves_existing_quote_plus_identity():
    uri = "http://sack.local/resource/kaggle/a+dataset/data.csv/a+column"

    assert normalize_uri(uri) == uri
    assert uri_to_resource_id(uri) == "kaggle/a+dataset/data.csv/a+column"
    assert resource_id_to_uri(uri_to_resource_id(uri)) == uri


@pytest.mark.parametrize(
    "uri",
    [
        "",
        " sack.local/resource/a",
        "http://sack.local/resource/raw space",
        "http://sack.local/resource/bad%2",
        "http:///missing-authority",
    ],
)
def test_invalid_uri_is_rejected_instead_of_repaired(uri):
    with pytest.raises(IdentifierError):
        normalize_uri(uri)


def test_unicode_nfc_has_one_identity():
    decomposed = "http://sack.local/resource/cafe\u0301"
    composed = "http://sack.local/resource/caf\u00e9"

    assert normalize_uri(decomposed) == composed
    assert vertex_uid(decomposed) == vertex_uid(composed)


def test_edge_uid_is_order_and_mapping_order_sensitive_as_expected():
    source = vertex_uid("http://sack.local/resource/source")
    target = vertex_uid("http://sack.local/resource/target")

    first = edge_uid(
        "HAS_PARAMETER",
        source,
        target,
        {"parameter": "sep", "position": 0},
    )
    same = edge_uid(
        "HAS_PARAMETER",
        source,
        target,
        {"position": 0, "parameter": "sep"},
    )
    reversed_edge = edge_uid(
        "HAS_PARAMETER",
        target,
        source,
        {"parameter": "sep", "position": 0},
    )

    assert first == same
    assert first != reversed_edge


def test_edge_uid_rejects_noncanonical_endpoint():
    canonical = vertex_uid("http://sack.local/resource/target")

    with pytest.raises(IdentifierError):
        edge_uid("IS_PART_OF", "not-a-uid", canonical)
