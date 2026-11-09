"""Versioned, read-only queries over published experiment reports."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from sack.paths import PROJECT_ROOT

MAX_FILE_BYTES = 8 * 1024 * 1024
STATES = {"running", "succeeded", "failed", "interrupted", "unknown"}
PUBLIC_FIELDS = (
    "schema_version", "experiment_name", "run_id", "status", "started_at",
    "completed_at", "report_ready", "report_sha256", "error_code", "source", "timestamp_source",
)


class ReportError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def component(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[\w][\w.-]{0,159}", value):
        raise ReportError("INVALID_ARGUMENT", "Names must be 1–160 letters, digits, underscores, dots or hyphens; paths are not accepted.")
    return value


def atomic_write(path: Path, content: bytes) -> None:
    """Publish only complete files; keep temporary files on the same filesystem."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".publish-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_manifest(path: Path, manifest: dict) -> None:
    atomic_write(path, (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


class ReportStore:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.environ.get("SACK_REPORT_ROOT") or
                         PROJECT_ROOT / "storage/experiment_reports").expanduser().resolve()

    def path(self, experiment_name: str, run_id: str | None = None, filename: str | None = None) -> Path:
        parts = [component(experiment_name)]
        if run_id is not None:
            parts.append(component(run_id))
        if filename is not None:
            if filename not in {"manifest.json", "research_report.md"}:
                raise ReportError("INVALID_ARGUMENT", "Unsupported report artifact.")
            parts.append(filename)
        current = self.root
        for part in parts:
            current = current / part
            if current.is_symlink():
                raise ReportError("UNSAFE_PATH", "Symbolic links are not allowed in the report archive.")
        if not current.resolve().is_relative_to(self.root):
            raise ReportError("UNSAFE_PATH", "Artifact is outside the configured report archive.")
        return current

    def read(self, path: Path, limit: int = MAX_FILE_BYTES) -> bytes:
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                import stat
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ReportError("CORRUPT_ARTIFACT", "Report artifact must be a regular file.")
                content = stream.read(limit + 1)
            if len(content) > limit:
                raise ReportError("ARTIFACT_TOO_LARGE", "Report artifact exceeds the configured size limit.")
            return content
        except FileNotFoundError:
            raise ReportError("ARTIFACT_MISSING", "The requested report artifact is missing.") from None
        except OSError:
            raise ReportError("ARTIFACT_UNREADABLE", "The requested report artifact cannot be read.") from None

    def manifest(self, experiment_name: str, run_id: str) -> dict:
        try:
            value = json.loads(self.read(self.path(experiment_name, run_id, "manifest.json"), 64 * 1024))
            if (not isinstance(value, dict) or value.get("schema_version") != 1 or
                    value.get("experiment_name") != experiment_name or value.get("run_id") != run_id or
                    value.get("status") not in STATES or not isinstance(value.get("started_at"), str) or
                    not isinstance(value.get("report_ready"), bool) or
                    (value["report_ready"] and (value["status"] != "succeeded" or
                     not re.fullmatch(r"[a-f0-9]{64}", str(value.get("report_sha256")))))):
                raise ValueError("Invalid manifest")
            return value
        except (ValueError, UnicodeError, TypeError) as exc:
            if isinstance(exc, ReportError):
                raise
            raise ReportError("CORRUPT_MANIFEST", "Experiment metadata is invalid.") from None

    @staticmethod
    def public(manifest: dict) -> dict:
        return {key: manifest.get(key) for key in PUBLIC_FIELDS}

    def runs(self, experiment_name: str) -> list[dict]:
        folder = self.path(experiment_name)
        if not folder.is_dir():
            raise ReportError("EXPERIMENT_NOT_FOUND", "No experiment with that exact name exists. Use list_experiments to search.")
        result = []
        for entry in sorted(folder.iterdir()):
            if entry.name.startswith("."):
                continue
            component(entry.name)
            path = self.path(experiment_name, entry.name)
            if path.is_dir() and (path / "manifest.json").exists():
                result.append(self.manifest(experiment_name, entry.name))
        return sorted(result, key=lambda row: (row["started_at"], row["run_id"]), reverse=True)

    def list_experiments(self, keyword: str = "", cursor: str | None = None, limit: int = 20) -> dict:
        if type(limit) is not int or not 1 <= limit <= 100 or len(keyword) > 160:
            raise ReportError("INVALID_ARGUMENT", "limit must be 1–100 and keyword at most 160 characters.")
        if cursor is not None:
            parts = cursor.split("/")
            if len(parts) != 2:
                raise ReportError("INVALID_ARGUMENT", "Invalid pagination cursor.")
            for part in parts:
                component(part)
        rows = []
        if self.root.is_dir():
            for entry in sorted(self.root.iterdir()):
                if entry.name.startswith(".") or keyword.casefold() not in entry.name.casefold():
                    continue
                component(entry.name)
                if self.path(entry.name).is_dir():
                    for run in self.runs(entry.name):
                        key = f"{entry.name}/{run['run_id']}"
                        if cursor is None or key > cursor:
                            rows.append((key, self.public(run)))
        rows.sort(key=lambda row: row[0])
        return {"experiments": [row[1] for row in rows[:limit]],
                "next_cursor": rows[limit - 1][0] if len(rows) > limit else None}

    def get_status(self, experiment_name: str, run_id: str | None = None) -> dict:
        runs = self.runs(experiment_name)
        if not runs:
            raise ReportError("EXPERIMENT_NOT_FOUND", "No recorded runs exist for this experiment.")
        if run_id is not None:
            component(run_id)
        chosen = next((r for r in runs if r["run_id"] == run_id), None) if run_id else runs[0]
        if chosen is None:
            raise ReportError("RUN_NOT_FOUND", "The requested run does not exist for this experiment.")
        latest_success = next((r for r in runs if r["status"] == "succeeded" and r["report_ready"]), None)
        return {**self.public(chosen), "latest_run": self.public(runs[0]),
                "latest_successful_run_id": latest_success["run_id"] if latest_success else None}

    def get_report(self, experiment_name: str, run_id: str | None = None,
                   offset: int = 0, max_chars: int = 20000) -> dict:
        if type(offset) is not int or offset < 0 or type(max_chars) is not int or not 1 <= max_chars <= 50000:
            raise ReportError("INVALID_ARGUMENT", "offset must be nonnegative and max_chars must be 1–50000.")
        if offset and run_id is None:
            raise ReportError("INVALID_ARGUMENT", "Specify run_id when reading subsequent report pages.")
        runs = self.runs(experiment_name)
        if not runs:
            raise ReportError("EXPERIMENT_NOT_FOUND", "No recorded runs exist for this experiment.")
        if run_id is not None:
            component(run_id)
        chosen = (next((r for r in runs if r["run_id"] == run_id), None) if run_id else
                  next((r for r in runs if r["status"] == "succeeded" and r["report_ready"]), None))
        if chosen is None:
            code = "RUN_NOT_FOUND" if run_id else "REPORT_NOT_READY"
            raise ReportError(code, "No published report matches this request. Use get_experiment_status for run details.")
        if chosen["status"] != "succeeded" or not chosen["report_ready"]:
            raise ReportError("REPORT_NOT_READY", "This run has no published final report.")
        content = self.read(self.path(experiment_name, chosen["run_id"], "research_report.md"))
        if hashlib.sha256(content).hexdigest() != chosen["report_sha256"]:
            raise ReportError("REPORT_INTEGRITY_ERROR", "The report no longer matches its published checksum.")
        try:
            text = content.decode("utf-8")
        except UnicodeError:
            raise ReportError("CORRUPT_ARTIFACT", "The report is not valid UTF-8.") from None
        if offset > len(text):
            raise ReportError("INVALID_ARGUMENT", "offset exceeds the report length.")
        end = min(len(text), offset + max_chars)
        return {**self.public(chosen), "format": "markdown", "content": text[offset:end],
                "offset": offset, "total_chars": len(text), "next_offset": end if end < len(text) else None,
                "latest_run": self.public(runs[0]), "is_latest_run": chosen["run_id"] == runs[0]["run_id"]}
