"""Read-only Cypher compatibility probes for the SACK TuGraph backend.

Run this after TuGraph is online and before enabling the Agent backend.  The
probes cover only the Cypher features used by ``TuGraphGraphStore`` and never
create, update, or delete graph data.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sack.knowledge.clients.tugraph_bolt import TuGraphBoltClient


class TuGraphCompatibilityError(RuntimeError):
    """Raised when one or more mandatory Cypher probes fail."""


ProbeValidator = Callable[[Sequence[Mapping[str, Any]]], None]


def _expect_single_value(expected: Any) -> ProbeValidator:
    def validate(rows: Sequence[Mapping[str, Any]]) -> None:
        if len(rows) != 1 or rows[0].get("value") != expected:
            raise ValueError(f"expected one row with value={expected!r}, got {rows!r}")

    return validate


def _expect_at_most(limit: int) -> ProbeValidator:
    def validate(rows: Sequence[Mapping[str, Any]]) -> None:
        if len(rows) > limit:
            raise ValueError(f"expected at most {limit} rows, got {len(rows)}")

    return validate


_UNICODE_VALUE = "SACK-图谱\nline-2"


def _probes() -> tuple[
    tuple[str, str, Mapping[str, Any], ProbeValidator], ...
]:
    """Return the immutable, read-only compatibility probe set."""

    return (
        (
            "bolt-round-trip",
            "RETURN 1 AS value",
            {},
            _expect_single_value(1),
        ),
        (
            "parameter-unicode-newline",
            "RETURN $value AS value",
            {"value": _UNICODE_VALUE},
            _expect_single_value(_UNICODE_VALUE),
        ),
        (
            "parameterized-limit",
            "MATCH (n) RETURN n.uid AS uid ORDER BY n.uid ASC LIMIT $row_limit",
            {"row_limit": 1},
            _expect_at_most(1),
        ),
        (
            "label-property-parameter",
            "MATCH (n:Dataset {uid: $uid}) RETURN n.uid AS uid LIMIT $row_limit",
            {"row_limit": 1, "uid": "compatibility-probe-does-not-exist"},
            _expect_at_most(1),
        ),
        (
            "pipeline-insight-match",
            """
MATCH (p:Pipeline)-[:HAS_CORE_INSIGHT]->(i:CoreInsight)
RETURN p.uid AS pipeline_uid, i.uid AS insight_uid
LIMIT $row_limit
""".strip(),
            {"row_limit": 1},
            _expect_at_most(1),
        ),
        (
            "phase-row-projection",
            """
MATCH (i:CoreInsight)-[:SPANS_PHASE]->(phase:Phase)
WHERE i.uid IN $insight_uids
RETURN i.uid AS insight_uid, phase.name AS phase_name
LIMIT $row_limit
""".strip(),
            {"insight_uids": ["compatibility-probe-does-not-exist"], "row_limit": 1},
            _expect_at_most(1),
        ),
        (
            "relationship-property-filter",
            """
MATCH ()-[r]->()
WHERE r.edge_uid IS NOT NULL
RETURN r.edge_uid AS edge_uid
LIMIT $row_limit
""".strip(),
            {"row_limit": 1},
            _expect_at_most(1),
        ),
    )


def check_tugraph_compatibility(
    *,
    result_dir: str | Path,
    client: Any | None = None,
    environ: Mapping[str, str] | None = None,
) -> Mapping[str, Any]:
    """Run SACK's mandatory read-only Cypher probes and persist the report."""

    values = os.environ if environ is None else environ
    owned_client = client is None
    if client is None:
        password = values.get("SACK_TUGRAPH_PASSWORD")
        if not password:
            raise TuGraphCompatibilityError("SACK_TUGRAPH_PASSWORD is required")
        client = TuGraphBoltClient(
            uri=values.get("SACK_TUGRAPH_BOLT_URL", "bolt://127.0.0.1:7687"),
            graph=values.get("SACK_TUGRAPH_GRAPH", "sack_poc"),
            user=values.get("SACK_TUGRAPH_USER", "admin"),
            password=password,
        )

    output_root = Path(result_dir).resolve()
    try:
        output_root.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        if owned_client:
            client.close()
        raise TuGraphCompatibilityError(
            f"Result directory already exists; refusing to overwrite: {output_root}"
        ) from exc

    checks: list[dict[str, Any]] = []
    try:
        for name, query, parameters, validator in _probes():
            try:
                rows = client.run(query, parameters)
                validator(rows)
            except Exception as exc:  # keep running to produce a complete report
                checks.append(
                    {
                        "error": f"{type(exc).__name__}: {exc}",
                        "name": name,
                        "status": "failed",
                    }
                )
            else:
                checks.append({"name": name, "status": "passed"})
    finally:
        if owned_client:
            client.close()

    failed = [check for check in checks if check["status"] == "failed"]
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "failed_check_count": len(failed),
        "graph": values.get("SACK_TUGRAPH_GRAPH", "sack_poc"),
        "probe_mode": "read-only",
        "status": "passed" if not failed else "failed",
        "target": {"database": "TuGraph", "version": "4.5.2"},
    }
    report_path = output_root / "compatibility_report.json"
    report_path.write_text(
        json.dumps(report, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    if failed:
        raise TuGraphCompatibilityError(
            f"TuGraph compatibility failed {len(failed)} probes; see {report_path}"
        )
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run read-only SACK Cypher compatibility probes against TuGraph."
    )
    parser.add_argument("--result-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report = check_tugraph_compatibility(result_dir=args.result_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
