"""Canonical identifiers shared by GraphDB, TuGraph, and pgvector.

Existing SACK URIs remain the external identity.  TuGraph uses a fixed-length
SHA-256 digest of the canonical URI as its primary key, while the complete URI
is retained as a regular property.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from typing import Any
from urllib.parse import urlsplit, urlunsplit


SACK_RESOURCE_PREFIX = "http://sack.local/resource/"
ID_CODEC_VERSION = "sha256-canonical-uri-v1"
VERTEX_UID_ALGORITHM = "sha256-uri-v1"
EDGE_UID_ALGORITHM = "sha256-edge-v1"

_PERCENT_ESCAPE_ERROR = re.compile(r"%(?![0-9A-Fa-f]{2})")
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*$")
_UID = re.compile(r"^[0-9a-f]{64}$")
_EDGE_TYPE = re.compile(r"^[A-Z][A-Z0-9_]*$")


class IdentifierError(ValueError):
    """Raised when an identifier cannot be made canonical without guessing."""


def normalize_uri(uri: str) -> str:
    """Return the conservative canonical form used for identity hashing.

    This function intentionally does not decode or re-encode paths.  Doing so
    would change identities already emitted by the RDF pipeline, especially
    where ``quote_plus`` encoded spaces as ``+``.  Only transformations that do
    not change HTTP URI semantics are applied: Unicode NFC, lowercase scheme,
    and lowercase authority.

    Invalid whitespace and malformed percent escapes are rejected instead of
    being silently repaired.  A caller that owns the source value must repair
    it before constructing a graph record.
    """

    if not isinstance(uri, str):
        raise IdentifierError("URI must be a string")

    normalized = unicodedata.normalize("NFC", uri)
    if not normalized:
        raise IdentifierError("URI must not be empty")
    if normalized != normalized.strip():
        raise IdentifierError("URI must not contain leading or trailing whitespace")
    if any(character.isspace() or ord(character) < 0x20 for character in normalized):
        raise IdentifierError("URI must not contain raw whitespace or control characters")
    if _PERCENT_ESCAPE_ERROR.search(normalized):
        raise IdentifierError("URI contains a malformed percent escape")

    parts = urlsplit(normalized)
    if not parts.scheme or not _SCHEME.fullmatch(parts.scheme):
        raise IdentifierError("URI must contain a valid scheme")
    if parts.scheme.lower() in {"http", "https"} and not parts.netloc:
        raise IdentifierError("HTTP(S) URI must contain an authority")

    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path,
            parts.query,
            parts.fragment,
        )
    )


def vertex_uid(uri: str) -> str:
    """Return the stable TuGraph primary key for a resource URI."""

    canonical_uri = normalize_uri(uri)
    return hashlib.sha256(canonical_uri.encode("utf-8")).hexdigest()


def is_uid(value: str) -> bool:
    """Return whether *value* is a lower-case SHA-256 hexadecimal digest."""

    return isinstance(value, str) and _UID.fullmatch(value) is not None


def _canonical_discriminator(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        raise IdentifierError("Edge discriminator must not contain NaN or infinity")
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise IdentifierError("Edge discriminator object keys must be strings")
        return {key: _canonical_discriminator(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_discriminator(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise IdentifierError(
        f"Unsupported edge discriminator type: {type(value).__name__}"
    )


def edge_uid(
    edge_type: str,
    src_uid: str,
    dst_uid: str,
    discriminator: Any = None,
) -> str:
    """Return a collision-safe deterministic identifier for an edge.

    ``discriminator`` distinguishes legitimate parallel edges.  It should
    describe identity (for example a parameter binding key), not mutable edge
    properties such as a similarity score.
    """

    if not isinstance(edge_type, str) or _EDGE_TYPE.fullmatch(edge_type) is None:
        raise IdentifierError(
            "Edge type must use upper snake case, for example IS_PART_OF"
        )
    if not is_uid(src_uid) or not is_uid(dst_uid):
        raise IdentifierError("Edge endpoints must be canonical vertex UIDs")

    payload = {
        "algorithm": EDGE_UID_ALGORITHM,
        "dst_uid": dst_uid,
        "edge_type": edge_type,
        "identity": _canonical_discriminator(discriminator),
        "src_uid": src_uid,
    }
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def resource_id_to_uri(resource_id: str) -> str:
    """Convert an existing encoded SACK resource id to its full URI.

    The function does not URL-encode the id.  Existing producers remain
    responsible for using the established ``quote_plus`` rules.
    """

    if not isinstance(resource_id, str) or not resource_id:
        raise IdentifierError("Resource id must be a non-empty string")
    if resource_id.startswith("/") or resource_id.endswith("/"):
        raise IdentifierError("Resource id must not start or end with a slash")
    return normalize_uri(f"{SACK_RESOURCE_PREFIX}{resource_id}")


def uri_to_resource_id(uri: str) -> str:
    """Return the encoded resource id from a SACK resource URI."""

    canonical_uri = normalize_uri(uri)
    if not canonical_uri.startswith(SACK_RESOURCE_PREFIX):
        raise IdentifierError(
            f"URI is outside the SACK resource namespace: {canonical_uri}"
        )
    resource_id = canonical_uri[len(SACK_RESOURCE_PREFIX) :]
    if not resource_id:
        raise IdentifierError("SACK resource URI does not contain a resource id")
    return resource_id
