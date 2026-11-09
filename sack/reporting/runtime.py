"""Track pipeline runs without importing the model or training runtime."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
from uuid import uuid4

from .store import MAX_FILE_BYTES, ReportError, ReportStore, atomic_write, component, write_manifest

_CURRENT_RUN: ContextVar = ContextVar("sack_report_run", default=None)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def workspace_lock(workspace: Path):
    """The pipeline still uses shared per-competition working files."""
    workspace = workspace.resolve(strict=True)
    with (workspace / ".sack-run.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ReportError("EXPERIMENT_BUSY", "Another run is using this experiment workspace.") from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


@contextmanager
def tracked_run(experiment_name: str, workspace: Path, root: str | Path | None = None):
    component(experiment_name)
    workspace = Path(workspace).resolve(strict=True)
    store = ReportStore(root)
    with workspace_lock(workspace):
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ_") + uuid4().hex[:12]
        manifest = dict(schema_version=1, experiment_name=experiment_name, run_id=run_id,
                        status="running", started_at=now(), completed_at=None,
                        report_ready=False, report_sha256=None, error_code=None, source="pipeline",
                        workspace=str(workspace), host=socket.gethostname(), pid=os.getpid())
        manifest_path = store.path(experiment_name, run_id, "manifest.json")
        write_manifest(manifest_path, manifest)
        session = dict(store=store, manifest=manifest, workspace=workspace, generated=False)
        token = _CURRENT_RUN.set(session)
        try:
            yield run_id
            if not session["generated"]:
                raise ReportError("REPORT_MISSING", "The completed pipeline did not generate a report for this run.")
            report = store.read(store.path(experiment_name, run_id, "research_report.md"))
            manifest.update(status="succeeded", completed_at=now(), report_ready=True,
                            report_sha256=hashlib.sha256(report).hexdigest())
            write_manifest(manifest_path, manifest)
        except BaseException as exc:
            manifest.update(status="interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "failed",
                            completed_at=now(), report_ready=False, report_sha256=None,
                            error_code=exc.code if isinstance(exc, ReportError) else type(exc).__name__)
            write_manifest(manifest_path, manifest)
            raise
        finally:
            _CURRENT_RUN.reset(token)


def save_research_report(workspace: str | Path, report: str) -> None:
    content = report.encode("utf-8")
    if not report.strip() or len(content) > MAX_FILE_BYTES:
        raise ReportError("INVALID_REPORT", "Final report must be nonempty and at most 8 MiB.")
    workspace = Path(workspace).resolve(strict=True)
    session = _CURRENT_RUN.get()
    if session is not None:
        if workspace != session["workspace"]:
            raise ReportError("RUN_MISMATCH", "Report workspace does not match the current run.")
        manifest = session["manifest"]
        atomic_write(session["store"].path(manifest["experiment_name"], manifest["run_id"], "research_report.md"), content)
        session["generated"] = True
    atomic_write(workspace / "research_report.md", content)


def import_report(store: ReportStore, experiment_name: str, report_path: Path,
                  evidence_path: Path | None = None) -> dict:
    """Import a historical snapshot; success requires a hash-bound operator receipt."""
    component(experiment_name)
    content = store.read(report_path)
    if not content.decode("utf-8").strip():
        raise ReportError("INVALID_REPORT", "Historical report is empty.")
    sha = hashlib.sha256(content).hexdigest()
    evidence_hash = ""
    if evidence_path:
        evidence_content = store.read(evidence_path, 64 * 1024)
        evidence = json.loads(evidence_content)
        if (not isinstance(evidence, dict) or evidence.get("accepted") is not True or
                evidence.get("errors") != [] or type(evidence.get("exit_code")) is not int or
                evidence["exit_code"] != 0 or evidence.get("report_sha256") != sha or
                not isinstance(evidence.get("completion_basis"), str) or not evidence["completion_basis"].strip()):
            raise ReportError("INVALID_EVIDENCE", "Completion receipt must contain accepted=true, errors=[], exit_code=0, report_sha256 and completion_basis.")
        evidence_hash = hashlib.sha256(evidence_content).hexdigest()
    run_id = "legacy_" + hashlib.sha256((sha + evidence_hash).encode()).hexdigest()[:24]
    folder = store.path(experiment_name, run_id)
    # Importers serialize on their own directory; the MCP reader never writes.
    store.root.mkdir(parents=True, exist_ok=True)
    with workspace_lock(store.root):
        if (folder / "manifest.json").exists():
            return store.public(store.manifest(experiment_name, run_id))
        timestamp = datetime.fromtimestamp(report_path.stat().st_mtime, timezone.utc).isoformat()
        manifest = dict(schema_version=1, experiment_name=experiment_name, run_id=run_id,
                        status="succeeded" if evidence_path else "unknown", started_at=timestamp,
                        completed_at=None, report_ready=bool(evidence_path), timestamp_source="report_mtime",
                        report_sha256=sha, error_code=None, source="historical_import",
                        evidence_sha256=evidence_hash or None)
        atomic_write(store.path(experiment_name, run_id, "research_report.md"), content)
        write_manifest(store.path(experiment_name, run_id, "manifest.json"), manifest)
    return store.public(manifest)


def recover_run(store: ReportStore, experiment_name: str, run_id: str, workspace: Path) -> dict:
    with workspace_lock(workspace):
        manifest = store.manifest(experiment_name, run_id)
        if manifest.get("workspace") != str(workspace.resolve()) or manifest.get("host") != socket.gethostname():
            raise ReportError("RUN_MISMATCH", "Recovery must run on the original host and workspace.")
        if manifest["status"] == "running":
            manifest.update(status="interrupted", completed_at=now(), report_ready=False,
                            error_code="PROCESS_INTERRUPTED")
            write_manifest(store.path(experiment_name, run_id, "manifest.json"), manifest)
        return store.public(manifest)
