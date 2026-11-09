import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from sack.reporting import ReportError, ReportStore, save_research_report, tracked_run
from sack.reporting.runtime import import_report, recover_run


@pytest.fixture
def archive(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return ReportStore(tmp_path / "reports"), workspace


def publish(store, workspace, text="# 最终报告\n模型结果。"):
    with tracked_run("titanic", workspace, store.root) as run_id:
        save_research_report(workspace, text)
        assert store.get_status("titanic")["report_ready"] is False
        with pytest.raises(ReportError, match="published"):
            store.get_report("titanic", run_id)
    return run_id


def test_report_is_published_only_after_success_and_matches_legacy(archive):
    store, workspace = archive
    run_id = publish(store, workspace)
    result = store.get_report("titanic")
    assert result["run_id"] == run_id
    assert result["content"] == (workspace / "research_report.md").read_text()
    assert result["report_sha256"] == hashlib.sha256(result["content"].encode()).hexdigest()
    assert "workspace" not in result and "pid" not in result


def test_failed_rerun_does_not_publish_draft_or_relabel_old_success(archive):
    store, workspace = archive
    old_id = publish(store, workspace, "# old report")
    with pytest.raises(RuntimeError):
        with tracked_run("titanic", workspace, store.root) as failed_id:
            save_research_report(workspace, "# unaccepted draft")
            raise RuntimeError("private error")
    result = store.get_report("titanic")
    assert result["run_id"] == old_id and result["content"] == "# old report"
    assert result["latest_run"]["status"] == "failed" and result["is_latest_run"] is False
    assert store.get_status("titanic")["latest_successful_run_id"] == old_id
    with pytest.raises(ReportError) as error:
        store.get_report("titanic", failed_id)
    assert error.value.code == "REPORT_NOT_READY"


def test_stale_working_report_never_satisfies_new_run(archive):
    store, workspace = archive
    publish(store, workspace)
    with pytest.raises(ReportError) as error:
        with tracked_run("titanic", workspace, store.root):
            pass
    assert error.value.code == "REPORT_MISSING"
    assert store.get_status("titanic")["status"] == "failed"


def test_snapshot_survives_rerun_and_pages_pin_version(archive):
    store, workspace = archive
    text = "# 报告\n" + "🙂验证结果。" * 30
    old_id = publish(store, workspace, text)
    first = store.get_report("titanic", max_chars=9)
    publish(store, workspace, "# new report")
    content = first["content"]
    offset = first["next_offset"]
    while offset is not None:
        result = store.get_report("titanic", old_id, offset=offset, max_chars=9)
        content += result["content"]
        offset = result["next_offset"]
    assert content == text
    assert store.get_report("titanic", old_id, len(text))["content"] == ""


@pytest.mark.parametrize("name", ["..", "../secret", "/etc/passwd", "a/b", "a\\b", "a\n", "", ".hidden", "x" * 161])
def test_path_traversal_names_are_rejected(archive, name):
    store, _ = archive
    with pytest.raises(ReportError) as error:
        store.get_report(name)
    assert error.value.code == "INVALID_ARGUMENT"


@pytest.mark.parametrize("target", ["experiment", "run", "manifest", "report"])
def test_symlinks_are_rejected_even_inside_archive(archive, target):
    store, workspace = archive
    run_id = publish(store, workspace)
    path = {"experiment": store.root / "titanic", "run": store.root / "titanic" / run_id,
            "manifest": store.root / "titanic" / run_id / "manifest.json",
            "report": store.root / "titanic" / run_id / "research_report.md"}[target]
    moved = path.with_name(path.name + "-moved")
    path.rename(moved)
    path.symlink_to(moved)
    with pytest.raises(ReportError) as error:
        store.get_report("titanic", run_id)
    assert error.value.code == "UNSAFE_PATH"


def test_integrity_and_missing_file_errors(archive):
    store, workspace = archive
    run_id = publish(store, workspace)
    path = store.path("titanic", run_id, "research_report.md")
    path.write_text("tampered")
    with pytest.raises(ReportError) as error:
        store.get_report("titanic")
    assert error.value.code == "REPORT_INTEGRITY_ERROR"
    path.unlink()
    with pytest.raises(ReportError) as error:
        store.get_report("titanic")
    assert error.value.code == "ARTIFACT_MISSING"


def test_workspace_lock_and_interruption_recovery(archive):
    store, workspace = archive
    with tracked_run("titanic", workspace, store.root) as run_id:
        with pytest.raises(ReportError) as error:
            with tracked_run("titanic", workspace, store.root):
                pass
        assert error.value.code == "EXPERIMENT_BUSY"
        with pytest.raises(ReportError) as error:
            recover_run(store, "titanic", run_id, workspace)
        assert error.value.code == "EXPERIMENT_BUSY"
        save_research_report(workspace, "# accepted")
    # A real killed process cannot run the context manager's exception handler.
    code = "from pathlib import Path; import os; from sack.reporting import tracked_run; "
    code += f"ctx=tracked_run('titanic', Path({str(workspace)!r}), {str(store.root)!r}); ctx.__enter__(); os._exit(9)"
    assert subprocess.run([sys.executable, "-c", code]).returncode == 9
    stale = store.get_status("titanic")
    assert stale["status"] == "running"
    assert recover_run(store, "titanic", stale["run_id"], workspace)["status"] == "interrupted"


def test_keyboard_interrupt_and_wrong_workspace(archive, tmp_path):
    store, workspace = archive
    with pytest.raises(KeyboardInterrupt):
        with tracked_run("titanic", workspace, store.root):
            raise KeyboardInterrupt()
    assert store.get_status("titanic")["status"] == "interrupted"
    with pytest.raises(ReportError) as error:
        with tracked_run("titanic", workspace, store.root):
            save_research_report(tmp_path, "wrong report")
    assert error.value.code == "RUN_MISMATCH"


def test_search_pagination_and_errors(archive):
    store, workspace = archive
    assert store.list_experiments()["experiments"] == []
    ids = {publish(store, workspace) for _ in range(3)}
    first = store.list_experiments(keyword="TITAN", limit=2)
    second = store.list_experiments(keyword="TITAN", cursor=first["next_cursor"], limit=2)
    assert {r["run_id"] for r in first["experiments"] + second["experiments"]} == ids
    assert second["next_cursor"] is None
    with pytest.raises(ReportError) as error:
        store.get_status("missing")
    assert error.value.code == "EXPERIMENT_NOT_FOUND"
    with pytest.raises(ReportError) as error:
        store.get_report("titanic", "missing")
    assert error.value.code == "RUN_NOT_FOUND"


@pytest.mark.parametrize("kwargs", [{"offset": -1}, {"offset": True}, {"offset": 999999}, {"max_chars": 0}, {"max_chars": 50001}])
def test_invalid_report_pagination(archive, kwargs):
    store, workspace = archive
    publish(store, workspace)
    with pytest.raises(ReportError) as error:
        store.get_report("titanic", **kwargs)
    assert error.value.code == "INVALID_ARGUMENT"


def test_historical_import_requires_hash_bound_completion_evidence(archive, tmp_path):
    store, _ = archive
    report = tmp_path / "legacy.md"
    report.write_text("# historical report")
    unknown = import_report(store, "legacy", report)
    assert unknown["status"] == "unknown" and not unknown["report_ready"]
    with pytest.raises(ReportError):
        store.get_report("legacy")
    evidence = tmp_path / "receipt.json"
    receipt = dict(accepted=True, errors=[], exit_code=0, report_sha256="wrong", completion_basis="verified original acceptance")
    evidence.write_text(json.dumps(receipt))
    with pytest.raises(ReportError) as error:
        import_report(store, "legacy", report, evidence)
    assert error.value.code == "INVALID_EVIDENCE"
    receipt["report_sha256"] = hashlib.sha256(report.read_bytes()).hexdigest()
    evidence.write_text(json.dumps(receipt))
    result = import_report(store, "legacy", report, evidence)
    assert result["status"] == "succeeded"
    assert import_report(store, "legacy", report, evidence)["run_id"] == result["run_id"]
    assert store.get_report("legacy")["content"] == report.read_text()


def test_incomplete_publication_is_not_listed_and_bad_metadata_is_rejected(archive):
    store, workspace = archive
    store.path("titanic", "unfinished").mkdir(parents=True)
    assert store.list_experiments()["experiments"] == []
    run_id = publish(store, workspace)
    path = store.path("titanic", run_id, "manifest.json")
    value = json.loads(path.read_text())
    value["status"] = ["succeeded"]
    path.write_text(json.dumps(value))
    with pytest.raises(ReportError) as error:
        store.get_report("titanic", run_id)
    assert error.value.code == "CORRUPT_MANIFEST"


def test_pipeline_entry_tracks_real_completion_boundary(archive, monkeypatch):
    from sack import framework
    store, workspace = archive
    workspace.rename(workspace.parent / "titanic")
    workspace = workspace.parent / "titanic"
    monkeypatch.setattr(framework, "COMPETITION_DATA_DIR", workspace.parent)
    monkeypatch.setenv("SACK_REPORT_ROOT", str(store.root))
    calls = []
    def pipeline(*args, **kwargs):
        calls.append(args)
        save_research_report(workspace, "# pipeline report")
    monkeypatch.setattr(framework, "_run_sack_pipeline", pipeline)
    framework.run_sack_pipeline("titanic", "Data Preparation", "Feature Engineering", "config.json")
    assert calls[0][0] == "titanic"
    assert store.get_report("titanic")["content"] == "# pipeline report"
