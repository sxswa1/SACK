import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from sack.knowledge.graph.model import VertexRecord
from sack.knowledge.graph.schema_registry import SCHEMA_VERSION
from sack.knowledge.graph.sinks.tugraph import export_tugraph_package
from sack.knowledge.migration.load_tugraph import (
    TuGraphLoadError,
    load_tugraph_package,
    verify_tugraph_package,
)


def _package(tmp_path):
    vertex = VertexRecord.from_uri(
        uri="http://sack.local/resource/dataset/server",
        label="Dataset",
        properties={"name": "server"},
        build_id="server-load-test",
    )
    package = tmp_path / "package"
    export_tugraph_package(
        (vertex,),
        (),
        package,
        source_schema_version=SCHEMA_VERSION,
    )
    return package


def _binary(tmp_path):
    path = tmp_path / "lgraph_import"
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_verify_tugraph_package_detects_tampering(tmp_path):
    package = _package(tmp_path)
    dataset_file = package / "vertices" / "dataset.jsonl"
    dataset_file.write_text("tampered\n", encoding="utf-8")

    with pytest.raises(TuGraphLoadError, match="mismatch"):
        verify_tugraph_package(package)


def test_dry_run_has_fail_closed_flags_and_writes_nothing(tmp_path):
    package = _package(tmp_path)
    result_dir = tmp_path / "result"

    result = load_tugraph_package(
        package_dir=package,
        database_dir=tmp_path / "database",
        result_dir=result_dir,
        graph_name="sack_poc",
        binary=_binary(tmp_path),
        dry_run=True,
    )

    assert result["preflight"] == "passed"
    assert result["dry_run"] is True
    assert result["command"][-2:] == ["--continue_on_error", "false"]
    assert "--overwrite" in result["command"]
    assert result["command"][result["command"].index("--overwrite") + 1] == "false"
    assert not result_dir.exists()


def test_loader_records_success_without_shell(monkeypatch, tmp_path):
    package = _package(tmp_path)
    binary = _binary(tmp_path)
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command[-1] == "--version":
            return SimpleNamespace(returncode=0, stdout="TuGraph 4.5.2\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="import ok\n", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    result_dir = tmp_path / "results"
    result = load_tugraph_package(
        package_dir=package,
        database_dir=tmp_path / "database",
        result_dir=result_dir,
        binary=binary,
    )

    assert result["status"] == "passed"
    assert result["return_code"] == 0
    assert calls[1][1]["cwd"] == package.resolve()
    assert calls[1][1]["check"] is False
    assert "shell" not in calls[1][1]
    saved = json.loads((result_dir / "import_result.json").read_text(encoding="utf-8"))
    assert saved["status"] == "passed"
    assert (result_dir / "lgraph_import.stdout.log").read_text(encoding="utf-8") == "import ok\n"


def test_loader_refuses_existing_database_without_overwrite(tmp_path):
    package = _package(tmp_path)
    database = tmp_path / "database"
    database.mkdir()

    with pytest.raises(TuGraphLoadError, match="already exists"):
        load_tugraph_package(
            package_dir=package,
            database_dir=database,
            result_dir=tmp_path / "results",
            binary=_binary(tmp_path),
            dry_run=True,
        )


def test_loader_rejects_unapproved_server_version(tmp_path):
    package = _package(tmp_path)

    with pytest.raises(TuGraphLoadError, match="must be 4.5.2"):
        load_tugraph_package(
            package_dir=package,
            database_dir=tmp_path / "database",
            result_dir=tmp_path / "results",
            binary=_binary(tmp_path),
            installed_version="4.6.0",
            dry_run=True,
        )


def test_loader_records_failure_before_raising(monkeypatch, tmp_path):
    package = _package(tmp_path)
    binary = _binary(tmp_path)

    def fake_run(command, **kwargs):
        if command[-1] == "--version":
            return SimpleNamespace(returncode=0, stdout="TuGraph 4.5.2\n", stderr="")
        return SimpleNamespace(returncode=7, stdout="", stderr="bad config\n")

    monkeypatch.setattr("subprocess.run", fake_run)
    result_dir = tmp_path / "results"
    with pytest.raises(TuGraphLoadError, match="exit code 7"):
        load_tugraph_package(
            package_dir=package,
            database_dir=tmp_path / "database",
            result_dir=result_dir,
            binary=binary,
        )

    result = json.loads((result_dir / "import_result.json").read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert result["return_code"] == 7
