"""Convert serialized Pipeline abstraction output to canonical graph records."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote_plus, unquote_plus

from sack.knowledge.graph.id_codec import normalize_uri, resource_id_to_uri, vertex_uid
from sack.knowledge.graph.model import EdgeRecord, VertexRecord


SACK_ONTOLOGY_PREFIX = "http://sack.local/ontology/"
SACK_RESOURCE_PREFIX = "http://sack.local/resource/"
LIBRARY_RESOURCE_PREFIX = f"{SACK_RESOURCE_PREFIX}library/"

_STATEMENT_SUFFIX = re.compile(r"^s([1-9][0-9]*)$")
_CALL_EDGE_TYPES = {
    "callsFunction": ("CALLS_FUNCTION", "Function"),
    "callsClass": ("CALLS_CLASS", "Class"),
    "callsPackage": ("CALLS_PACKAGE", "Package"),
    "callsLibrary": ("CALLS_LIBRARY", "Library"),
    "callsAPI": ("CALLS_API", "API"),
}
_READ_EDGE_TYPES = {
    "readsTable": ("READS_TABLE", "Table"),
    "readsColumn": ("READS_COLUMN", "Column"),
}
_ONTOLOGY_LABELS = {
    f"{SACK_ONTOLOGY_PREFIX}Library": "Library",
    f"{SACK_ONTOLOGY_PREFIX}Package": "Package",
    f"{SACK_ONTOLOGY_PREFIX}Class": "Class",
    f"{SACK_ONTOLOGY_PREFIX}Function": "Function",
    f"{SACK_ONTOLOGY_PREFIX}API": "API",
    None: "API",
}


class PipelineBuildError(ValueError):
    """Raised when Pipeline abstraction output is incomplete or contradictory."""


@dataclass(frozen=True, slots=True)
class PipelineRecords:
    vertices: tuple[VertexRecord, ...]
    edges: tuple[EdgeRecord, ...]


class _Accumulator:
    def __init__(self) -> None:
        self.vertices: dict[str, VertexRecord] = {}
        self.edges: dict[str, EdgeRecord] = {}

    def add_vertex(self, record: VertexRecord) -> VertexRecord:
        existing = self.vertices.get(record.uid)
        if existing is not None and existing != record:
            raise PipelineBuildError(f"Conflicting vertex records for {record.uri}")
        self.vertices[record.uid] = record
        return record

    def add_edge(self, record: EdgeRecord) -> EdgeRecord:
        existing = self.edges.get(record.edge_uid)
        if existing is not None and existing != record:
            raise PipelineBuildError(f"Conflicting edge records for {record.edge_uid}")
        self.edges[record.edge_uid] = record
        return record

    def result(self) -> PipelineRecords:
        return PipelineRecords(
            vertices=tuple(sorted(self.vertices.values(), key=lambda item: (item.label, item.uid))),
            edges=tuple(sorted(self.edges.values(), key=lambda item: (item.edge_type, item.edge_uid))),
        )


def _compact(properties: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in properties.items() if value is not None}


def _uri(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise PipelineBuildError("Pipeline resource URI must be a non-empty string")
    if "://" in value:
        return normalize_uri(value)
    return resource_id_to_uri(value)


def _rdf_types(label: str) -> str:
    return json.dumps(
        [f"{SACK_ONTOLOGY_PREFIX}{label}"],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _required_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PipelineBuildError(f"{name} must be an object")
    return value


def _required_sequence(value: Any, name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise PipelineBuildError(f"{name} must be an array")
    return value


def _optional_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise PipelineBuildError(f"{field_name} must be an integer")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise PipelineBuildError(f"{field_name} must be an integer") from exc
    if not math.isfinite(number) or not number.is_integer():
        raise PipelineBuildError(f"{field_name} must be a finite integer")
    return int(number)


def _optional_float(value: Any, field_name: str) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise PipelineBuildError(f"{field_name} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise PipelineBuildError(f"{field_name} must be numeric") from exc
    if not math.isfinite(number):
        raise PipelineBuildError(f"{field_name} must be finite")
    return number


def _normalized_name(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PipelineBuildError(f"{field_name} must be a non-empty string")
    return " ".join(value.split()).casefold()


def _new_resource_uri(kind: str, name: str) -> str:
    return f"{SACK_RESOURCE_PREFIX}{kind}/{quote_plus(name)}"


def _qualified_library_name(uri: str) -> str:
    canonical = _uri(uri)
    if canonical.startswith(LIBRARY_RESOURCE_PREFIX):
        path = canonical[len(LIBRARY_RESOURCE_PREFIX) :]
        return unquote_plus(path).replace("/", ".")
    return canonical


def _statement_ordinal(uri: str) -> int:
    suffix = _uri(uri).rsplit("/", 1)[-1]
    match = _STATEMENT_SUFFIX.fullmatch(suffix)
    if match is None:
        raise PipelineBuildError(f"Statement URI must end in s<number>: {uri}")
    return int(match.group(1))


def _edge(
    *,
    edge_type: str,
    source: VertexRecord,
    target: VertexRecord,
    build_id: str,
    scope_uid: str | None = None,
    properties: Mapping[str, Any] | None = None,
    discriminator: Any = None,
) -> EdgeRecord:
    return EdgeRecord.from_endpoints(
        edge_type=edge_type,
        src_uid=source.uid,
        dst_uid=target.uid,
        properties=properties or {},
        build_id=build_id,
        scope_uid=scope_uid,
        discriminator=discriminator,
    )


def _reference_vertex(uri: str, label: str, build_id: str, **properties: Any) -> VertexRecord:
    return VertexRecord.from_uri(
        uri=_uri(uri),
        label=label,
        properties=_compact({"rdf_types_json": _rdf_types(label), **properties}),
        build_id=build_id,
    )


def _walk_libraries(
    libraries: Mapping[str, Any] | Sequence[Any],
) -> Iterable[tuple[Mapping[str, Any], str | None]]:
    roots = libraries.values() if isinstance(libraries, Mapping) else libraries

    def walk(item: Any, parent_uri: str | None) -> Iterable[tuple[Mapping[str, Any], str | None]]:
        library = _required_mapping(item, "library")
        yield library, parent_uri
        children = library.get("contain", ())
        for child in _required_sequence(children, "library.contain"):
            yield from walk(child, library.get("uri"))

    for root in roots:
        yield from walk(root, None)


def _library_label(type_uri: Any) -> str:
    try:
        return _ONTOLOGY_LABELS[type_uri]
    except KeyError as exc:
        raise PipelineBuildError(f"Unsupported API type URI: {type_uri!r}") from exc


def _add_library_tree(
    accumulator: _Accumulator,
    libraries: Mapping[str, Any] | Sequence[Any],
    build_id: str,
) -> dict[str, str]:
    labels_by_uri: dict[str, str] = {}
    pending_membership: list[tuple[str, str]] = []
    for item, parent_uri in _walk_libraries(libraries):
        uri = _uri(item.get("uri"))
        label = _library_label(item.get("type"))
        labels_by_uri[uri] = label
        accumulator.add_vertex(
            _reference_vertex(
                uri,
                label,
                build_id,
                qualified_name=_qualified_library_name(uri),
            )
        )
        if parent_uri is not None:
            pending_membership.append((uri, _uri(parent_uri)))

    for child_uri, parent_uri in pending_membership:
        child = accumulator.vertices[vertex_uid(child_uri)]
        parent = accumulator.vertices.get(vertex_uid(parent_uri))
        if parent is None:
            raise PipelineBuildError(f"Library parent is missing: {parent_uri}")
        accumulator.add_edge(
            _edge(
                edge_type="IS_PART_OF",
                source=child,
                target=parent,
                build_id=build_id,
            )
        )
    return labels_by_uri


def _add_file_elements(
    accumulator: _Accumulator,
    file_elements: Sequence[Mapping[str, Any]],
    build_id: str,
) -> None:
    for raw_table in file_elements:
        table_data = _required_mapping(raw_table, "file element")
        table = accumulator.add_vertex(
            _reference_vertex(table_data.get("uri"), "Table", build_id)
        )
        for raw_column in _required_sequence(table_data.get("contain", ()), "file element.contain"):
            column_data = _required_mapping(raw_column, "column file element")
            column = accumulator.add_vertex(
                _reference_vertex(column_data.get("uri"), "Column", build_id)
            )
            accumulator.add_edge(
                _edge(
                    edge_type="IS_PART_OF",
                    source=column,
                    target=table,
                    build_id=build_id,
                )
            )


def _pipeline_vertex(pipeline: Mapping[str, Any], build_id: str) -> VertexRecord:
    title = pipeline.get("title")
    return VertexRecord.from_uri(
        uri=_uri(pipeline.get("uri")),
        label="Pipeline",
        properties=_compact(
            {
                "display_label": title,
                "rdf_types_json": _rdf_types("Pipeline"),
                "title": title,
                "author": pipeline.get("author"),
                "votes": _optional_int(pipeline.get("votes"), "votes"),
                "written_on_raw": pipeline.get("date"),
                "source_url": pipeline.get("url"),
                "score": _optional_float(pipeline.get("score"), "score"),
            }
        ),
        build_id=build_id,
    )


def _add_tags(
    accumulator: _Accumulator,
    pipeline: VertexRecord,
    tags: Sequence[Any],
    build_id: str,
) -> None:
    for raw_tag in tags:
        normalized = _normalized_name(raw_tag, "tag")
        tag = accumulator.add_vertex(
            _reference_vertex(
                _new_resource_uri("tag", normalized),
                "Tag",
                build_id,
                name=normalized,
                normalized_name=normalized,
            )
        )
        accumulator.add_edge(
            _edge(
                edge_type="HAS_TAG",
                source=pipeline,
                target=tag,
                build_id=build_id,
            )
        )


def _parameter_value(value: Any) -> tuple[str, str]:
    if isinstance(value, str):
        return value, "string"
    if value is None:
        return "None", "null"
    if isinstance(value, bool):
        return str(value), "boolean"
    if isinstance(value, int):
        return str(value), "integer"
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PipelineBuildError("Parameter value must not be NaN or infinity")
        return str(value), "float"
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True), "json"


def _add_statement_relations(
    accumulator: _Accumulator,
    statement: VertexRecord,
    node: Mapping[str, Any],
    pipeline: VertexRecord,
    library_labels: Mapping[str, str],
    build_id: str,
) -> None:
    scope_uid = pipeline.uid
    for raw_call in _required_sequence(node.get("calls", ()), "statement.calls"):
        call = _required_mapping(raw_call, "statement call")
        call_type = call.get("call_type")
        try:
            edge_type, fallback_label = _CALL_EDGE_TYPES[call_type]
        except KeyError as exc:
            raise PipelineBuildError(f"Unsupported statement call type: {call_type!r}") from exc
        uri = _uri(call.get("uri"))
        target_label = library_labels.get(uri, fallback_label)
        target = accumulator.add_vertex(
            _reference_vertex(
                uri,
                target_label,
                build_id,
                qualified_name=_qualified_library_name(uri),
            )
        )
        accumulator.add_edge(
            _edge(
                edge_type=edge_type,
                source=statement,
                target=target,
                build_id=build_id,
                scope_uid=scope_uid,
            )
        )

    for raw_read in _required_sequence(node.get("read", ()), "statement.read"):
        read = _required_mapping(raw_read, "statement read")
        read_type = read.get("type")
        try:
            edge_type, target_label = _READ_EDGE_TYPES[read_type]
        except KeyError as exc:
            raise PipelineBuildError(f"Unsupported statement read type: {read_type!r}") from exc
        target = accumulator.add_vertex(
            _reference_vertex(read.get("uri"), target_label, build_id)
        )
        accumulator.add_edge(
            _edge(
                edge_type=edge_type,
                source=statement,
                target=target,
                build_id=build_id,
                scope_uid=scope_uid,
            )
        )

    for raw_flow in _required_sequence(node.get("control_flow", ()), "statement.control_flow"):
        control_uri = _uri(raw_flow)
        control = accumulator.add_vertex(
            _reference_vertex(
                control_uri,
                "ControlFlow",
                build_id,
                kind=control_uri.rsplit("/", 1)[-1],
            )
        )
        accumulator.add_edge(
            _edge(
                edge_type="IN_CONTROL_FLOW",
                source=statement,
                target=control,
                build_id=build_id,
                scope_uid=scope_uid,
            )
        )

    for raw_parameter in _required_sequence(node.get("parameters", ()), "statement.parameters"):
        binding = _required_mapping(raw_parameter, "statement parameter")
        name = _normalized_name(binding.get("parameter"), "parameter")
        value, value_type = _parameter_value(binding.get("parameter_value"))
        parameter = accumulator.add_vertex(
            _reference_vertex(
                _new_resource_uri("parameter", name),
                "Parameter",
                build_id,
                name=name,
            )
        )
        accumulator.add_edge(
            _edge(
                edge_type="HAS_PARAMETER",
                source=statement,
                target=parameter,
                build_id=build_id,
                scope_uid=scope_uid,
                properties={"value": value, "value_type": value_type},
                discriminator=name,
            )
        )


def _target_statement(
    accumulator: _Accumulator,
    uri: Any,
    relation_name: str,
) -> VertexRecord:
    target = accumulator.vertices.get(vertex_uid(_uri(uri)))
    if target is None or target.label != "Statement":
        raise PipelineBuildError(f"{relation_name} references a missing Statement: {uri}")
    return target


def _add_statement_flow_edges(
    accumulator: _Accumulator,
    statement_by_uri: Mapping[str, tuple[VertexRecord, Mapping[str, Any]]],
    pipeline: VertexRecord,
    build_id: str,
) -> None:
    for statement_uri, (statement, node) in statement_by_uri.items():
        next_uri = node.get("next")
        if next_uri:
            target = _target_statement(accumulator, next_uri, "next")
            accumulator.add_edge(
                _edge(
                    edge_type="NEXT_STATEMENT",
                    source=statement,
                    target=target,
                    build_id=build_id,
                    scope_uid=pipeline.uid,
                )
            )
        for target_uri in _required_sequence(node.get("dataFlow", ()), "statement.dataFlow"):
            target = _target_statement(accumulator, target_uri, "data flow")
            accumulator.add_edge(
                _edge(
                    edge_type="DATA_FLOW_TO",
                    source=statement,
                    target=target,
                    build_id=build_id,
                    scope_uid=pipeline.uid,
                )
            )


def _iter_insights(core_insights: Mapping[str, Any]) -> Iterable[tuple[str, Mapping[str, Any]]]:
    phase_insights = core_insights.get("phase_insights", {}) or {}
    if not isinstance(phase_insights, Mapping):
        raise PipelineBuildError("core_insights.phase_insights must be an object")
    for phase, insights in phase_insights.items():
        for insight in _required_sequence(insights, f"phase_insights.{phase}"):
            yield str(phase), _required_mapping(insight, "core insight")
    for insight in _required_sequence(
        core_insights.get("cross_phase_insights", ()) or (),
        "core_insights.cross_phase_insights",
    ):
        yield "Cross-Phase", _required_mapping(insight, "cross-phase insight")


def _add_core_insights(
    accumulator: _Accumulator,
    core_insights: Mapping[str, Any],
    pipeline: VertexRecord,
    build_id: str,
) -> None:
    for phase, data in _iter_insights(core_insights):
        insight_id = data.get("insight_id")
        if not isinstance(insight_id, str) or not insight_id:
            raise PipelineBuildError("CoreInsight is missing insight_id")
        insight = accumulator.add_vertex(
            VertexRecord.from_uri(
                uri=f"{pipeline.uri}/insight/{quote_plus(insight_id)}",
                label="CoreInsight",
                properties=_compact(
                    {
                        "rdf_types_json": _rdf_types("CoreInsight"),
                        "insight_id": insight_id,
                        "description": data.get("description"),
                        "insight_type": data.get("type"),
                        "effectiveness": data.get("effectiveness_reasoning"),
                        "significance": data.get("significance"),
                        "transferability": data.get("transferability"),
                        "evidence": data.get("evidence"),
                        "phase": "CrossPhase" if phase == "Cross-Phase" else phase,
                    }
                ),
                build_id=build_id,
            )
        )
        accumulator.add_edge(
            _edge(
                edge_type="HAS_CORE_INSIGHT",
                source=pipeline,
                target=insight,
                build_id=build_id,
                scope_uid=pipeline.uid,
            )
        )
        for node_id in _required_sequence(
            data.get("implementing_node_ids", ()),
            "core insight implementing_node_ids",
        ):
            statement_uri = f"{pipeline.uri}/{node_id}"
            statement = _target_statement(accumulator, statement_uri, "CoreInsight")
            accumulator.add_edge(
                _edge(
                    edge_type="IMPLEMENTED_IN",
                    source=insight,
                    target=statement,
                    build_id=build_id,
                    scope_uid=pipeline.uid,
                )
            )
        for raw_phase in _required_sequence(
            data.get("spanning_phases", ()) or (),
            "core insight spanning_phases",
        ):
            if not isinstance(raw_phase, str) or not raw_phase.strip():
                raise PipelineBuildError("spanning phase must be a non-empty string")
            phase_vertex = accumulator.add_vertex(
                _reference_vertex(
                    _new_resource_uri("phase", raw_phase),
                    "Phase",
                    build_id,
                    name=raw_phase,
                )
            )
            accumulator.add_edge(
                _edge(
                    edge_type="SPANS_PHASE",
                    source=insight,
                    target=phase_vertex,
                    build_id=build_id,
                )
            )


def build_pipeline_records(
    *,
    pipeline_info: Mapping[str, Any],
    nodes: Sequence[Mapping[str, Any]],
    file_elements: Sequence[Mapping[str, Any]],
    libraries: Mapping[str, Any] | Sequence[Any],
    core_insights: Mapping[str, Any] | None,
    build_id: str,
) -> PipelineRecords:
    """Build one Pipeline subgraph while retaining former Named Graph scope."""

    pipeline_data = _required_mapping(pipeline_info, "pipeline_info")
    accumulator = _Accumulator()
    pipeline = accumulator.add_vertex(_pipeline_vertex(pipeline_data, build_id))
    dataset = accumulator.add_vertex(
        _reference_vertex(pipeline_data.get("dataset"), "Dataset", build_id)
    )
    accumulator.add_edge(
        _edge(
            edge_type="IS_PART_OF",
            source=pipeline,
            target=dataset,
            build_id=build_id,
        )
    )
    _add_tags(
        accumulator,
        pipeline,
        _required_sequence(pipeline_data.get("tags", ()), "pipeline tags"),
        build_id,
    )
    library_labels = _add_library_tree(accumulator, libraries, build_id)
    _add_file_elements(accumulator, file_elements, build_id)

    statement_by_uri: dict[str, tuple[VertexRecord, Mapping[str, Any]]] = {}
    for raw_node in nodes:
        node = _required_mapping(raw_node, "statement")
        uri = _uri(node.get("uri"))
        if uri in statement_by_uri:
            raise PipelineBuildError(f"Duplicate Statement URI: {uri}")
        statement = accumulator.add_vertex(
            VertexRecord.from_uri(
                uri=uri,
                label="Statement",
                properties=_compact(
                    {
                        "rdf_types_json": _rdf_types("Statement"),
                        "text": node.get("text"),
                        "phase": node.get("phase"),
                        "ordinal": _statement_ordinal(uri),
                        "pipeline_uid": pipeline.uid,
                    }
                ),
                build_id=build_id,
            )
        )
        statement_by_uri[uri] = (statement, node)
        accumulator.add_edge(
            _edge(
                edge_type="IS_PART_OF",
                source=statement,
                target=pipeline,
                build_id=build_id,
                scope_uid=pipeline.uid,
            )
        )

    for statement, node in statement_by_uri.values():
        _add_statement_relations(
            accumulator,
            statement,
            node,
            pipeline,
            library_labels,
            build_id,
        )
    _add_statement_flow_edges(accumulator, statement_by_uri, pipeline, build_id)
    if core_insights:
        _add_core_insights(
            accumulator,
            _required_mapping(core_insights, "core_insights"),
            pipeline,
            build_id,
        )
    return accumulator.result()


def build_pipeline_records_from_metadata(
    metadata: Mapping[str, Any],
    *,
    build_id: str,
    complete_analysis: Mapping[str, Any] | None = None,
) -> PipelineRecords:
    """Rebuild a Pipeline CIR subgraph from versioned persisted artifacts.

    Metadata written before version 2 contains only record counts and cannot be
    used as a lossless migration source.  Such artifacts are rejected with an
    explicit rebuild instruction instead of producing a partial graph.
    """

    document = _required_mapping(metadata, "pipeline metadata")
    version = document.get("metadata_version", 1)
    if version != 2 or "nodes" not in document or "file_elements" not in document:
        raise PipelineBuildError(
            "Pipeline metadata predates lossless version 2; rerun Pipeline abstraction "
            "or export the accepted Named Graph from GraphDB"
        )
    analysis = complete_analysis or {}
    core_insights = analysis.get("core_insights")
    return build_pipeline_records(
        pipeline_info=_required_mapping(document.get("pipeline_info"), "pipeline_info"),
        nodes=_required_sequence(document.get("nodes"), "pipeline metadata nodes"),
        file_elements=_required_sequence(
            document.get("file_elements"), "pipeline metadata file_elements"
        ),
        libraries=document.get("libraries", {}),
        core_insights=None
        if core_insights is None
        else _required_mapping(core_insights, "complete analysis core_insights"),
        build_id=build_id,
    )
