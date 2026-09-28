import json

import pytest

from sack.knowledge.migration.check_tugraph_compatibility import (
    TuGraphCompatibilityError,
    check_tugraph_compatibility,
)


class FakeClient:
    def __init__(self, *, fail_query_number=None):
        self.fail_query_number = fail_query_number
        self.queries = []

    def run(self, query, parameters=None):
        self.queries.append((query, parameters))
        if len(self.queries) == self.fail_query_number:
            raise RuntimeError("unsupported syntax")
        if query == "RETURN 1 AS value":
            return [{"value": 1}]
        if query == "RETURN $value AS value":
            return [{"value": parameters["value"]}]
        return []

    def close(self):
        raise AssertionError("Injected clients must not be closed")


def test_compatibility_probes_are_read_only_and_parameterized(tmp_path):
    client = FakeClient()
    report = check_tugraph_compatibility(
        result_dir=tmp_path / "compatibility",
        client=client,
        environ={"SACK_TUGRAPH_GRAPH": "fixture"},
    )

    assert report["status"] == "passed"
    assert report["graph"] == "fixture"
    assert len(client.queries) == 7
    assert all(
        token not in query.upper()
        for query, _ in client.queries
        for token in ("CREATE ", "DELETE ", "DETACH ", "MERGE ", " SET ")
    )
    assert any("LIMIT $row_limit" in query for query, _ in client.queries)
    assert any(
        parameters.get("value") == "SACK-图谱\nline-2"
        for _, parameters in client.queries
    )


def test_compatibility_failure_is_recorded_before_raising(tmp_path):
    result_dir = tmp_path / "compatibility"

    with pytest.raises(TuGraphCompatibilityError, match="failed 1 probes"):
        check_tugraph_compatibility(
            result_dir=result_dir,
            client=FakeClient(fail_query_number=3),
        )

    report = json.loads(
        (result_dir / "compatibility_report.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "failed"
    assert report["failed_check_count"] == 1
    assert report["checks"][2]["name"] == "parameterized-limit"
    assert "unsupported syntax" in report["checks"][2]["error"]


def test_compatibility_refuses_to_overwrite_results(tmp_path):
    result_dir = tmp_path / "compatibility"
    result_dir.mkdir()

    with pytest.raises(TuGraphCompatibilityError, match="refusing to overwrite"):
        check_tugraph_compatibility(
            result_dir=result_dir,
            client=FakeClient(),
        )
