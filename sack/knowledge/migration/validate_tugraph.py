"""Read-only post-import integrity checks for a running TuGraph 4.5.2 graph."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from sack.knowledge.clients.tugraph_bolt import TuGraphBoltClient
from sack.knowledge.graph.schema_registry import EDGE_SCHEMAS, VERTEX_SCHEMAS
from sack.knowledge.migration.load_tugraph import verify_tugraph_package


class TuGraphValidationError(RuntimeError):
    """Raised when the loaded graph differs from its export preflight report."""


_ENDPOINT_KEY = re.compile(r"^([A-Z][A-Z0-9_]*):([A-Za-z0-9_]+)->([A-Za-z0-9_]+)$")


def _load_object(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TuGraphValidationError(f"Cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise TuGraphValidationError(f"JSON document must be an object: {path}")
    return value


def _count(client: Any, query: str) -> int:
    rows = client.run(query, {})
    if len(rows) != 1:
        raise TuGraphValidationError(
            f"Count query returned {len(rows)} rows instead of one: {query}"
        )
    value = rows[0].get("count")
    if isinstance(value, bool) or not isinstance(value, int):
        raise TuGraphValidationError(f"Count query returned a non-integer: {value!r}")
    return value


def _check(
    checks: list[dict[str, Any]],
    *,
    name: str,
    expected: int,
    actual: int,
) -> None:
    checks.append(
        {
            "actual": actual,
            "expected": expected,
            "name": name,
            "status": "passed" if actual == expected else "failed",
        }
    )


def validate_loaded_tugraph(
    *,
    package_dir: str | Path,
    result_dir: str | Path,
    client: Any | None = None,
    environ: Mapping[str, str] | None = None,
) -> Mapping[str, Any]:
    """Compare live counts and scope invariants with the immutable package."""

    package_root = Path(package_dir).resolve()
    manifest = verify_tugraph_package(package_root)
    preflight = _load_object(package_root / "validation_report.json")
    values = os.environ if environ is None else environ
    owned_client = client is None
    if client is None:
        password = values.get("SACK_TUGRAPH_PASSWORD")
        if not password:
            raise TuGraphValidationError("SACK_TUGRAPH_PASSWORD is required")
        client = TuGraphBoltClient(
            uri=values.get("SACK_TUGRAPH_BOLT_URL", "bolt://127.0.0.1:7687"),
            graph=values.get("SACK_TUGRAPH_GRAPH", "sack_poc"),
            user=values.get("SACK_TUGRAPH_USER", "admin"),
            password=password,
        )

    results = Path(result_dir).resolve()
    try:
        results.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        if owned_client:
            client.close()
        raise TuGraphValidationError(
            f"Result directory already exists; refusing to overwrite: {results}"
        ) from exc

    checks: list[dict[str, Any]] = []
    try:
        vertex_counts = preflight.get("vertex_count_by_label")
        edge_counts = preflight.get("edge_count_by_label")
        endpoint_counts = preflight.get("edge_count_by_endpoint_pair")
        if not all(isinstance(value, Mapping) for value in (vertex_counts, edge_counts, endpoint_counts)):
            raise TuGraphValidationError("Preflight count sections must be objects")

        for label, expected in sorted(vertex_counts.items()):
            if label not in VERTEX_SCHEMAS or not isinstance(expected, int):
                raise TuGraphValidationError(f"Invalid vertex count entry: {label!r}")
            actual = _count(client, f"MATCH (n:{label}) RETURN count(n) AS count")
            _check(checks, name=f"vertex:{label}", expected=expected, actual=actual)

        for edge_type, expected in sorted(edge_counts.items()):
            if edge_type not in EDGE_SCHEMAS or not isinstance(expected, int):
                raise TuGraphValidationError(f"Invalid edge count entry: {edge_type!r}")
            actual = _count(
                client,
                f"MATCH ()-[r:{edge_type}]->() RETURN count(r) AS count",
            )
            _check(checks, name=f"edge:{edge_type}", expected=expected, actual=actual)

        for key, expected in sorted(endpoint_counts.items()):
            match = _ENDPOINT_KEY.fullmatch(str(key))
            if match is None or not isinstance(expected, int):
                raise TuGraphValidationError(f"Invalid endpoint count entry: {key!r}")
            edge_type, source_label, target_label = match.groups()
            schema = EDGE_SCHEMAS.get(edge_type)
            if (
                schema is None
                or source_label not in VERTEX_SCHEMAS
                or target_label not in VERTEX_SCHEMAS
                or (source_label, target_label) not in schema.endpoint_pairs
            ):
                raise TuGraphValidationError(f"Endpoint entry is outside the registry: {key}")
            actual = _count(
                client,
                f"MATCH (s:{source_label})-[r:{edge_type}]->(d:{target_label}) "
                "RETURN count(r) AS count",
            )
            _check(checks, name=f"endpoint:{key}", expected=expected, actual=actual)

        for edge_type in sorted(edge_counts):
            schema = EDGE_SCHEMAS[edge_type]
            if not schema.scope_required:
                continue
            missing_scope = _count(
                client,
                f"MATCH ()-[r:{edge_type}]->() "
                "WHERE r.scope_uid IS NULL RETURN count(r) AS count",
            )
            _check(
                checks,
                name=f"scope-present:{edge_type}",
                expected=0,
                actual=missing_scope,
            )
            if "Statement" in schema.src_labels:
                mismatch = _count(
                    client,
                    f"MATCH (s:Statement)-[r:{edge_type}]->() "
                    "WHERE r.scope_uid <> s.pipeline_uid RETURN count(r) AS count",
                )
                _check(
                    checks,
                    name=f"source-statement-scope:{edge_type}",
                    expected=0,
                    actual=mismatch,
                )
            if "Statement" in schema.dst_labels:
                mismatch = _count(
                    client,
                    f"MATCH ()-[r:{edge_type}]->(s:Statement) "
                    "WHERE r.scope_uid <> s.pipeline_uid RETURN count(r) AS count",
                )
                _check(
                    checks,
                    name=f"target-statement-scope:{edge_type}",
                    expected=0,
                    actual=mismatch,
                )
    finally:
        if owned_client:
            client.close()

    failed = [item for item in checks if item["status"] == "failed"]
    report = {
        "build_id": manifest.get("build_id"),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "failed_check_count": len(failed),
        "status": "passed" if not failed else "failed",
        "target": manifest.get("target"),
    }
    report_path = results / "post_import_validation.json"
    report_path.write_text(
        json.dumps(report, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    if failed:
        raise TuGraphValidationError(
            f"Post-import validation failed {len(failed)} checks; see {report_path}"
        )
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a running TuGraph graph against an immutable import package."
    )
    parser.add_argument("--package-dir", required=True, type=Path)
    parser.add_argument("--result-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report = validate_loaded_tugraph(
        package_dir=args.package_dir,
        result_dir=args.result_dir,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
