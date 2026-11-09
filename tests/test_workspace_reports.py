import hashlib
import json

import pytest

from sack.reporting import ReportError, save_research_report, tracked_run
from sack.reporting.workspaces import WorkspaceStore


@pytest.fixture
def workspaces(tmp_path):
    root = tmp_path / "experiments"
    root.mkdir()
    return WorkspaceStore(root, tmp_path / "history")


def workspace(store, name="titanic"):
    path = store.root / name
    path.mkdir(exist_ok=True)
    return path


def publish(store, path, text="# final"):
    with tracked_run(path.name, path, store.archive.root) as run_id:
        save_research_report(path, text)
    return run_id


def test_lists_original_directories_without_requiring_import(workspaces):
    store = workspaces
    for name in ["titanic", "house-prices", "spaceship-titanic"]:
        workspace(store, name)
    (store.root / "README.txt").write_text("ignored")
    result = store.list_experiments(limit=2)
    assert len(result["experiments"]) == 2
    assert all(r["status"] == "unknown" and not r["report_ready"] for r in result["experiments"])
    more = store.list_experiments(cursor=result["next_cursor"], limit=2)
    assert len(more["experiments"]) == 1 and more["next_cursor"] is None
    assert store.list_experiments(keyword="SPACE")["experiments"][0]["experiment_name"] == "spaceship-titanic"


def test_report_reads_original_file_and_detects_changed_content(workspaces):
    store = workspaces
    path = workspace(store)
    run_id = publish(store, path)
    result = store.get_report("titanic")
    assert result["content"] == "# final" and result["run_id"] == run_id
    assert result["report_source"] == "workspace" and result["is_latest_run"]
    assert "workspace" not in result
    (path / "research_report.md").write_text("tampered")
    with pytest.raises(ReportError) as error:
        store.get_report("titanic")
    assert error.value.code == "REPORT_INTEGRITY_ERROR"


def test_failed_rerun_does_not_hide_history_or_change_original_workspace(workspaces):
    store = workspaces
    path = workspace(store)
    old = publish(store, path, "# old report")
    first = store.get_report("titanic", max_chars=3)
    with pytest.raises(RuntimeError):
        with tracked_run(path.name, path, store.archive.root):
            save_research_report(path, "# failed draft")
            raise RuntimeError("failure")
    result = store.get_report("titanic")
    assert result["run_id"] == old and result["latest_run"]["status"] == "failed"
    assert result["report_source"] == "history" and not result["is_latest_run"]
    rest = store.get_report("titanic", first["run_id"], first["next_offset"])
    assert first["content"] + rest["content"] == "# old report"
    assert [p.name for p in store.root.iterdir()] == ["titanic"]
    assert len(store.list_experiments()["experiments"]) == 1


def test_existing_report_without_completion_evidence_is_visible_but_unverified(workspaces):
    store = workspaces
    path = workspace(store)
    (path / "research_report.md").write_text("# old file")
    status = store.get_status("titanic")
    assert status["report_available"] and not status["completion_verified"]
    with pytest.raises(ReportError) as error:
        store.get_report("titanic")
    assert error.value.code == "REPORT_NOT_READY"


def test_restored_report_preserves_failed_eda_and_metrics(workspaces):
    store = workspaces
    path = workspace(store, "ghouls")
    text = "# Historical report"
    (path / "research_report.md").write_text(text)
    provenance = dict(experiment_name="ghouls", dsp_completed=True, training_completed=True,
                      report_sha256=hashlib.sha256(text.encode()).hexdigest(), acceptance_passed=False,
                      acceptance_errors=["Independent EDA did not succeed"], eda_status="fail",
                      validation_metric="f1_weighted", validation_score=0.7513900709219858,
                      started_at="2026-10-29T08:03:22+00:00", completed_at="2026-10-29T14:01:23+00:00")
    (path / "report_provenance.json").write_text(json.dumps(provenance))
    result = store.get_report("ghouls")
    assert result["content"] == text and result["report_source"] == "workspace"
    assert result["acceptance_passed"] is False and result["eda_status"] == "fail"
    assert result["validation_score"] == provenance["validation_score"]
    assert not result["is_latest_run"]
    (path / "research_report.md").write_text("# changed")
    with pytest.raises(ReportError) as error:
        store.get_report("ghouls")
    assert error.value.code == "REPORT_INTEGRITY_ERROR"


@pytest.mark.parametrize("artifact", ["workspace", "research_report.md", "run_manifest.json", "report_provenance.json"])
def test_original_directory_symlinks_are_rejected(workspaces, tmp_path, artifact):
    store = workspaces
    path = workspace(store)
    target = tmp_path / "outside"
    target.mkdir()
    link = path if artifact == "workspace" else path / artifact
    if artifact == "workspace":
        path.rmdir()
    link.symlink_to(target)
    with pytest.raises(ReportError) as error:
        store.get_status("titanic")
    assert error.value.code == "UNSAFE_PATH"


def test_workspace_metadata_cannot_claim_another_directory(workspaces):
    store = workspaces
    path = workspace(store)
    publish(store, path)
    meta = path / "run_manifest.json"
    value = json.loads(meta.read_text())
    value["workspace"] = "/elsewhere"
    meta.write_text(json.dumps(value))
    with pytest.raises(ReportError) as error:
        store.get_report("titanic")
    assert error.value.code == "RUN_MISMATCH"
