"""Discover experiments in their existing workspaces, including unarchived tasks."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re

from sack.paths import COMPETITION_DATA_DIR
from .store import ReportError, ReportStore, component


class WorkspaceStore:
    def __init__(self, root: str | Path | None = None, archive_root: str | Path | None = None):
        self.root = Path(root or os.environ.get("SACK_EXPERIMENT_ROOT") or COMPETITION_DATA_DIR).expanduser().resolve()
        self.archive = ReportStore(archive_root)

    def path(self, name: str, filename: str | None = None) -> Path:
        folder = self.root / component(name)
        if folder.is_symlink() or not folder.resolve().is_relative_to(self.root):
            raise ReportError("UNSAFE_PATH", "Experiment workspace must not be a symbolic link.")
        if not folder.is_dir():
            raise ReportError("EXPERIMENT_NOT_FOUND", "No experiment with that exact name exists in the experiment directory.")
        path = folder / filename if filename else folder
        if path.is_symlink():
            raise ReportError("UNSAFE_PATH", "Experiment artifacts must not be symbolic links.")
        return path

    def current(self, name: str) -> dict:
        path = self.path(name, "run_manifest.json")
        report_exists = self.path(name, "research_report.md").is_file()
        if not path.exists():
            return dict(experiment_name=name, run_id=None, status="unknown", report_ready=False,
                        report_available=report_exists, completion_verified=False, source="workspace",
                        error_code=None, started_at=None, completed_at=None)
        content = self.archive.read(path, 64 * 1024)
        try:
            run_id = component(json.loads(content)["run_id"])
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise ReportError("CORRUPT_MANIFEST", "Workspace run metadata is invalid.") from None
        value = self.archive.parse_manifest(content, name, run_id)
        if value.get("workspace") != str(self.path(name).resolve()):
            raise ReportError("RUN_MISMATCH", "Run metadata belongs to a different experiment workspace.")
        return {**self.archive.public(value), "report_available": report_exists,
                "completion_verified": value["status"] == "succeeded" and value["report_ready"]}

    def history(self, name: str) -> list[dict]:
        try:
            runs = self.archive.runs(name)
        except ReportError as exc:
            if exc.code == "EXPERIMENT_NOT_FOUND":
                runs = []
            else:
                raise
        restored = self.restored(name)
        if restored and not any(r["run_id"] == restored["run_id"] for r in runs):
            runs.append(restored)
        return sorted(runs, key=lambda r: (r.get("started_at") or "", r["run_id"]), reverse=True)

    def restored(self, name: str) -> dict | None:
        path = self.path(name, "report_provenance.json")
        if not path.exists():
            return None
        try:
            value = json.loads(self.archive.read(path, 64 * 1024))
            if (not isinstance(value, dict) or value.get("experiment_name") != name or
                    value.get("dsp_completed") is not True or value.get("training_completed") is not True or
                    not re.fullmatch(r"[a-f0-9]{64}", str(value.get("report_sha256"))) or
                    not isinstance(value.get("acceptance_passed"), bool) or
                    not isinstance(value.get("acceptance_errors"), list) or
                    not isinstance(value.get("started_at"), str) or not isinstance(value.get("completed_at"), str) or
                    type(value.get("validation_score")) not in (int, float) or not math.isfinite(value["validation_score"])):
                raise ValueError("Invalid provenance")
        except (ValueError, UnicodeError, TypeError):
            raise ReportError("CORRUPT_MANIFEST", "Restored report provenance is invalid.") from None
        return dict(schema_version=1, experiment_name=name, run_id="report_" + value["report_sha256"][:24],
                    status="succeeded", report_ready=True, source="historical_restore", error_code=None,
                    report_sha256=value["report_sha256"], started_at=value["started_at"], completed_at=value["completed_at"],
                    **{key: value.get(key) for key in ("training_completed", "acceptance_passed", "eda_status",
                                                     "validation_metric", "validation_score", "acceptance_errors")})

    def list_experiments(self, keyword: str = "", cursor: str | None = None, limit: int = 20) -> dict:
        if type(limit) is not int or not 1 <= limit <= 100 or len(keyword) > 160:
            raise ReportError("INVALID_ARGUMENT", "limit must be 1–100 and keyword at most 160 characters.")
        if cursor is not None:
            component(cursor)
        rows = []
        if self.root.is_dir():
            for folder in sorted(self.root.iterdir()):
                if folder.name.startswith(".") or keyword.casefold() not in folder.name.casefold():
                    continue
                if not folder.is_dir() and not folder.is_symlink():
                    continue
                component(folder.name)
                if self.path(folder.name).is_dir() and (cursor is None or folder.name > cursor):
                    rows.append(self.get_status(folder.name, include_runs=False))
                    if len(rows) > limit:
                        break
        return {"experiments": rows[:limit], "next_cursor": rows[limit - 1]["experiment_name"] if len(rows) > limit else None}

    def get_status(self, experiment_name: str, run_id: str | None = None, *, include_runs: bool = True) -> dict:
        current = self.current(experiment_name)
        runs = self.history(experiment_name)
        chosen = current
        if run_id is not None:
            component(run_id)
            if run_id != current["run_id"]:
                chosen = next((self.archive.public(r) for r in runs if r["run_id"] == run_id), None)
                if chosen is None:
                    raise ReportError("RUN_NOT_FOUND", "The requested run does not exist for this experiment.")
        latest_success = next((r for r in runs if r["status"] == "succeeded" and r["report_ready"]), None)
        success_id = (current["run_id"] if current["status"] == "succeeded" and current["report_ready"] else
                      latest_success["run_id"] if latest_success else None)
        result = {**chosen, "latest_run": current, "latest_successful_run_id": success_id, "recorded_runs": len(runs)}
        result["available_report"] = (self.archive.public(current) if current["status"] == "succeeded" and current["report_ready"] else
                                      self.archive.public(latest_success) if latest_success else None)
        if include_runs:
            result.update(recent_runs=[self.archive.public(r) for r in runs[:20]], has_more_runs=len(runs) > 20)
        return result

    def get_report(self, experiment_name: str, run_id: str | None = None,
                   offset: int = 0, max_chars: int = 20000) -> dict:
        if type(offset) is not int or offset < 0 or type(max_chars) is not int or not 1 <= max_chars <= 50000:
            raise ReportError("INVALID_ARGUMENT", "offset must be nonnegative and max_chars must be 1–50000.")
        if offset and run_id is None:
            raise ReportError("INVALID_ARGUMENT", "Specify run_id when reading subsequent report pages.")
        if run_id is not None:
            component(run_id)
        current = self.current(experiment_name)
        chosen = None
        if current["status"] == "succeeded" and current["report_ready"] and (run_id is None or run_id == current["run_id"]):
            chosen = current
        else:
            chosen = next((r for r in self.history(experiment_name) if r["status"] == "succeeded" and r["report_ready"] and
                           (run_id is None or run_id == r["run_id"])), None)
        if chosen is None:
            if run_id is not None and any(r["run_id"] == run_id for r in self.history(experiment_name)):
                raise ReportError("REPORT_NOT_READY", "This run has no verified final report.")
            if run_id is not None:
                raise ReportError("RUN_NOT_FOUND", "No recorded run matches the requested run_id.")
            raise ReportError("REPORT_NOT_READY", "The experiment exists but has no verified final report. Check get_experiment_status.")
        matches_workspace = False
        content = None
        if current["report_available"]:
            content = self.archive.read(self.path(experiment_name, "research_report.md"))
            matches_workspace = hashlib.sha256(content).hexdigest() == chosen["report_sha256"]
            if not matches_workspace and chosen["run_id"] == current["run_id"]:
                raise ReportError("REPORT_INTEGRITY_ERROR", "The workspace report does not match its completed run.")
        if matches_workspace:
            try:
                text = content.decode("utf-8")
            except UnicodeError:
                raise ReportError("CORRUPT_ARTIFACT", "The workspace report is not valid UTF-8.") from None
            if offset > len(text):
                raise ReportError("INVALID_ARGUMENT", "offset exceeds the report length.")
            end = min(len(text), offset + max_chars)
            return {**self.archive.public(chosen), "completion_verified": True, "format": "markdown", "content": text[offset:end], "offset": offset,
                    "total_chars": len(text), "next_offset": end if end < len(text) else None,
                    "latest_run": current, "is_latest_run": chosen["run_id"] == current["run_id"], "report_source": "workspace"}
        try:
            result = self.archive.get_report(experiment_name, chosen["run_id"], offset, max_chars)
        except ReportError as exc:
            if chosen["source"] == "historical_restore" and exc.code in {"EXPERIMENT_NOT_FOUND", "RUN_NOT_FOUND"}:
                raise ReportError("REPORT_INTEGRITY_ERROR", "The restored report is missing or no longer matches its provenance.") from None
            if exc.code == "EXPERIMENT_NOT_FOUND":
                raise ReportError("REPORT_NOT_READY", "The experiment exists but has no verified final report. Check get_experiment_status.") from None
            raise
        return {**result, "latest_run": current, "is_latest_run": result["run_id"] == current["run_id"],
                "report_source": "history"}
