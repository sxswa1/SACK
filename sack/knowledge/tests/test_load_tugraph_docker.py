import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from sack.knowledge.graph.model import VertexRecord
from sack.knowledge.graph.schema_registry import SCHEMA_VERSION
from sack.knowledge.graph.sinks.tugraph import export_tugraph_package
from sack.knowledge.migration.load_tugraph import TuGraphLoadError
from sack.knowledge.migration.load_tugraph_docker import IMAGE_DIGEST, load_tugraph_docker


@pytest.fixture
def package(tmp_path):
    root = tmp_path / "package"
    vertex = VertexRecord.from_uri(
        uri="http://sack.local/docker/test", label="Dataset",
        properties={"name": "fixture"}, build_id="docker-test",
    )
    export_tugraph_package((vertex,), (), root, source_schema_version=SCHEMA_VERSION)
    return root


def _docker(monkeypatch, *, digest=IMAGE_DIGEST, arch="amd64", fail=False, timeout=False):
    calls = []
    monkeypatch.setattr("shutil.which", lambda value: "/usr/bin/docker")

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if "inspect" in command:
            return SimpleNamespace(returncode=0, stdout=json.dumps([{
                "Id": "sha256:local-image", "RepoDigests": ["mirror/image@" + digest],
                "Os": "linux", "Architecture": arch,
            }]), stderr="")
        if "rm" in command:
            return SimpleNamespace(returncode=0, stdout="removed", stderr="")
        if timeout:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        kwargs["stdout"].write("Import finished\n")
        kwargs["stderr"].write("bad import\n" if fail else "")
        return SimpleNamespace(returncode=7 if fail else 0)

    monkeypatch.setattr("subprocess.run", run)
    return calls


def _load(package, tmp_path, **kwargs):
    return load_tugraph_docker(
        package_dir=package, database_dir=tmp_path / "database",
        result_dir=tmp_path / "results", **kwargs,
    )


def test_docker_dry_run_is_read_only_and_pinned(monkeypatch, package, tmp_path):
    calls = _docker(monkeypatch)
    monkeypatch.setenv("DOCKER_HOST", "tcp://untrusted:2375")
    report = _load(package, tmp_path, dry_run=True)
    assert not (tmp_path / "results").exists()
    assert not (tmp_path / "database").exists()
    assert len(calls) == 1
    assert "DOCKER_HOST" not in calls[0][1]["env"]
    assert report["image"]["digest"] == IMAGE_DIGEST
    command = report["command"]
    assert command[1:3] == ["--context", "default"]
    assert command[command.index("--pull") + 1] == "never"
    assert command[command.index("--network") + 1] == "none"
    assert "sha256:local-image" in command
    assert "--password" not in command
    assert "--privileged" not in command
    assert command[-4:] == ["--overwrite", "false", "--continue_on_error", "false"]


def test_success_copies_package_and_records_logs(monkeypatch, package, tmp_path):
    before = {p.relative_to(package): p.read_bytes() for p in package.rglob("*") if p.is_file()}
    calls = _docker(monkeypatch)
    report = _load(package, tmp_path)
    assert report["status"] == "passed"
    assert (tmp_path / "database").is_dir()
    results = tmp_path / "results"
    assert json.loads((results / "import_result.json").read_text())["return_code"] == 0
    assert (results / "lgraph_import.stdout.log").read_text() == "Import finished\n"
    assert (results / "work" / "import.config.json").read_bytes() == before[Path("import.config.json")]
    assert before == {p.relative_to(package): p.read_bytes() for p in package.rglob("*") if p.is_file()}
    command, kwargs = calls[1]
    assert "shell" not in kwargs
    assert str(package) not in " ".join(command)
    assert str(results / "work") in " ".join(command)


@pytest.mark.parametrize("target", ["database", "results"])
def test_existing_targets_are_never_overwritten(monkeypatch, package, tmp_path, target):
    calls = _docker(monkeypatch)
    (tmp_path / target).mkdir()
    with pytest.raises(TuGraphLoadError, match="refusing overwrite"):
        _load(package, tmp_path)
    assert calls == []


def test_overlapping_directories_rejected(monkeypatch, package, tmp_path):
    calls = _docker(monkeypatch)
    with pytest.raises(TuGraphLoadError, match="disjoint"):
        load_tugraph_docker(package_dir=package, database_dir=package / "database", result_dir=tmp_path / "results")
    assert calls == []


@pytest.mark.parametrize("option,match", [({"digest": "sha256:wrong"}, "digest"), ({"arch": "arm64"}, "amd64")])
def test_unapproved_image_rejected(monkeypatch, package, tmp_path, option, match):
    _docker(monkeypatch, **option)
    with pytest.raises(TuGraphLoadError, match=match):
        _load(package, tmp_path)
    assert not (tmp_path / "database").exists()


def test_tampered_package_rejected_before_docker(monkeypatch, package, tmp_path):
    calls = _docker(monkeypatch)
    (package / "vertices" / "dataset.jsonl").write_text("tampered")
    with pytest.raises(TuGraphLoadError, match="mismatch"):
        _load(package, tmp_path)
    assert calls == []


def test_symlink_package_rejected(monkeypatch, package, tmp_path):
    calls = _docker(monkeypatch)
    (package / "extra-link").symlink_to(tmp_path)
    with pytest.raises(TuGraphLoadError, match="symlinks"):
        _load(package, tmp_path)
    assert calls == []


def test_failure_keeps_evidence_and_partial_database(monkeypatch, package, tmp_path):
    _docker(monkeypatch, fail=True)
    with pytest.raises(TuGraphLoadError, match="Docker import failed"):
        _load(package, tmp_path)
    report = json.loads((tmp_path / "results" / "import_result.json").read_text())
    assert report["status"] == "failed" and report["return_code"] == 7
    assert (tmp_path / "database").exists()
    assert (tmp_path / "results" / "work").exists()


def test_changed_package_during_copy_never_imported(monkeypatch, package, tmp_path):
    from sack.knowledge.migration import load_tugraph_docker as loader

    calls = _docker(monkeypatch)
    original_verify = loader.verify_tugraph_package

    def verify(path):
        manifest = original_verify(path)
        if Path(path).name == "work":
            return {**manifest, "build_id": "changed-during-copy"}
        return manifest

    monkeypatch.setattr(loader, "verify_tugraph_package", verify)
    with pytest.raises(TuGraphLoadError, match="Docker import failed"):
        _load(package, tmp_path)
    assert len(calls) == 1  # Only image inspection; no importer started.
    report = json.loads((tmp_path / "results" / "import_result.json").read_text())
    assert report["status"] == "failed"
    assert "changed during workspace preparation" in report["error"]


def test_timeout_stops_only_owned_import_container(monkeypatch, package, tmp_path):
    calls = _docker(monkeypatch, timeout=True)
    with pytest.raises(TuGraphLoadError, match="Docker import failed"):
        _load(package, tmp_path)
    report = json.loads((tmp_path / "results" / "import_result.json").read_text())
    assert report["status"] == "timed_out"
    cleanup = calls[-1][0]
    assert cleanup[-3:] == ["rm", "--force", report["container"]]
    assert report["container"].startswith("sack-import-")


@pytest.mark.parametrize("options", [{"graph_name": "bad/name"}, {"memory": "0g"}, {"cpus": 0}, {"timeout_seconds": float("nan")}])
def test_invalid_options_rejected(monkeypatch, package, tmp_path, options):
    calls = _docker(monkeypatch)
    with pytest.raises(TuGraphLoadError):
        _load(package, tmp_path, **options)
    assert calls == []
