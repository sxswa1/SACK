"""Storage-neutral graph primitives for SACK knowledge backends.

The modules in this package deliberately have no GraphDB, TuGraph, pandas, or
network dependencies.  They form the compatibility boundary shared by RDF and
labelled-property-graph sinks.
"""

from sack.knowledge.graph.id_codec import (
    ID_CODEC_VERSION,
    SACK_RESOURCE_PREFIX,
    IdentifierError,
    edge_uid,
    normalize_uri,
    resource_id_to_uri,
    uri_to_resource_id,
    vertex_uid,
)
from sack.knowledge.graph.model import EdgeRecord, RecordValidationError, VertexRecord
from sack.knowledge.graph.merge import MergedGraphRecords, RecordMergeError, merge_graph_records
from sack.knowledge.graph.package_writer import CanonicalPackageWriter, PackageWriteError
from sack.knowledge.graph.package_reader import (
    CanonicalGraphPackage,
    PackageReadError,
    read_canonical_package,
)

__all__ = [
    "SACK_RESOURCE_PREFIX",
    "ID_CODEC_VERSION",
    "EdgeRecord",
    "IdentifierError",
    "CanonicalPackageWriter",
    "CanonicalGraphPackage",
    "PackageWriteError",
    "PackageReadError",
    "MergedGraphRecords",
    "RecordMergeError",
    "RecordValidationError",
    "VertexRecord",
    "edge_uid",
    "normalize_uri",
    "resource_id_to_uri",
    "uri_to_resource_id",
    "vertex_uid",
    "merge_graph_records",
    "read_canonical_package",
]
