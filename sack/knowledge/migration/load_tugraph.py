"""Fail-closed server-side loader for a verified TuGraph import package.

The loader uses offline full import and never invokes a shell.  Overwriting is
disabled unless the operator passes ``--overwrite`` explicitly.  It records
the exact command, version probe, elapsed time, return code, and output logs in
a separate result directory so the immutable import package remains unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Mapping, Sequence

from sack.knowledge.graph.sinks.tugraph import TUGRAPH_TARGET_VERSION


class TuGraphLoadError(RuntimeError):
    """Raised when preflight or ``lgraph_import`` fails."""


_GRAPH_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _load_object(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TuGraphLoadError(f"Cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise TuGraphLoadError(f"JSON document must be an object: {path}")
    return value


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_tugraph_package(package_dir: str | Path) -> Mapping[str, Any]:
    """Verify completion marker, version, every artifact hash, and file path."""

    root = Path(package_dir).resolve()
    if not root.is_dir():
        raise TuGraphLoadError(f"TuGraph package directory does not exist: {root}")
    if (root / ".incomplete").exists():
        raise TuGraphLoadError(f"TuGraph package is incomplete: {root}")
    manifest_path = root / "manifest.json"
    manifest = _load_object(manifest_path)
    expected_target = f"TuGraph {TUGRAPH_TARGET_VERSION}"
    if manifest.get("target") != expected_target:
        raise TuGraphLoadError(
            f"TuGraph target mismatch: expected {expected_target!r}, "
            f"found {manifest.get('target')!r}"
        )
    raw_artifacts = manifest.get("artifacts")
    if not isinstance(raw_artifacts, list):
        raise TuGraphLoadError("manifest.artifacts must be an array")

    artifact_paths: set[str] = set()
    for artifact in raw_artifacts:
        if not isinstance(artifact, Mapping):
            raise TuGraphLoadError("Each manifest artifact must be an object")
        relative_path = artifact.get("relative_path")
        if not isinstance(relative_path, str) or not relative_path:
            raise TuGraphLoadError("Artifact relative_path must be a non-empty string")
        if relative_path in artifact_paths:
            raise TuGraphLoadError(f"Duplicate artifact path: {relative_path}")
        artifact_paths.add(relative_path)
        path = (root / relative_path).resolve()
        if root not in path.parents or not path.is_file():
            raise TuGraphLoadError(f"Artifact is missing or escapes package: {relative_path}")
        size = path.stat().st_size
        if artifact.get("byte_count") != size:
            raise TuGraphLoadError(f"Artifact byte count mismatch: {relative_path}")
        if artifact.get("sha256") != _digest(path):
            raise TuGraphLoadError(f"Artifact digest mismatch: {relative_path}")

    if "import.config.json" not in artifact_paths:
        raise TuGraphLoadError("Manifest does not include import.config.json")
    config = _load_object(root / "import.config.json")
    files = config.get("files")
    if not isinstance(files, list):
        raise TuGraphLoadError("import.config.json files must be an array")
    for file_config in files:
        if not isinstance(file_config, Mapping):
            raise TuGraphLoadError("Each TuGraph file configuration must be an object")
        relative_path = file_config.get("path")
        if relative_path not in artifact_paths:
            raise TuGraphLoadError(
                f"Configured import file is not covered by manifest: {relative_path!r}"
            )
    return manifest


def _resolve_binary(binary: str | Path) -> Path:
    candidate = str(binary)
    if "/" in candidate:
        path = Path(candidate).expanduser().resolve()
        if not path.is_file() or not os.access(path, os.X_OK):
            raise TuGraphLoadError(f"lgraph_import is not executable: {path}")
        return path
    resolved = shutil.which(candidate)
    if resolved is None:
        raise TuGraphLoadError(f"Cannot find lgraph_import binary: {candidate}")
    return Path(resolved).resolve()


def _validate_database_dir(database_dir: str | Path, *, overwrite: bool) -> Path:
    path = Path(database_dir).expanduser().resolve()
    if path == Path(path.anchor) or path == Path.home().resolve():
        raise TuGraphLoadError(f"Refusing unsafe database directory: {path}")
    if path.exists() and not overwrite:
        raise TuGraphLoadError(
            f"Database directory already exists; pass --overwrite explicitly: {path}"
        )
    return path


def build_import_command(
    *,
    binary: Path,
    database_dir: Path,
    graph_name: str,
    overwrite: bool,
) -> list[str]:
    if _GRAPH_NAME.fullmatch(graph_name) is None:
        raise TuGraphLoadError(
            "graph_name must contain only letters, numbers, underscores, and hyphens"
        )
    return [
        str(binary),
        "--online",
        "false",
        "--config_file",
        "import.config.json",
        "--dir",
        str(database_dir),
        "--graph",
        graph_name,
        "--overwrite",
        "true" if overwrite else "false",
        "--continue_on_error",
        "false",
    ]


def _write_result(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def load_tugraph_package(
    *,
    package_dir: str | Path,
    database_dir: str | Path,
    result_dir: str | Path,
    graph_name: str = "sack",
    binary: str | Path = "lgraph_import",
    installed_version: str = TUGRAPH_TARGET_VERSION,
    overwrite: bool = False,
    dry_run: bool = False,
) -> Mapping[str, Any]:
    """Verify and optionally execute TuGraph 4.5.2 offline full import."""

    package_root = Path(package_dir).resolve()
    manifest = verify_tugraph_package(package_root)
    if installed_version != TUGRAPH_TARGET_VERSION:
        raise TuGraphLoadError(
            f"Server TuGraph version must be {TUGRAPH_TARGET_VERSION}, "
            f"found declaration {installed_version!r}"
        )
    binary_path = _resolve_binary(binary)
    database_path = _validate_database_dir(database_dir, overwrite=overwrite)
    command = build_import_command(
        binary=binary_path,
        database_dir=database_path,
        graph_name=graph_name,
        overwrite=overwrite,
    )
    if dry_run:
        return {
            "build_id": manifest.get("build_id"),
            "command": command,
            "database_dir": str(database_path),
            "dry_run": True,
            "graph": graph_name,
            "installed_version": installed_version,
            "package_dir": str(package_root),
            "preflight": "passed",
            "target": manifest.get("target"),
        }

    results = Path(result_dir).resolve()
    try:
        results.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise TuGraphLoadError(
            f"Result directory already exists; refusing to overwrite: {results}"
        ) from exc

    version_probe = subprocess.run(
        [str(binary_path), "--version"],
        cwd=package_root,
        capture_output=True,
        text=True,
        check=False,
    )
    started_at = datetime.now(timezone.utc)
    started_clock = monotonic()
    completed = subprocess.run(
        command,
        cwd=package_root,
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed = monotonic() - started_clock
    ended_at = datetime.now(timezone.utc)
    stdout_path = results / "lgraph_import.stdout.log"
    stderr_path = results / "lgraph_import.stderr.log"
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    result = {
        "binary": str(binary_path),
        "build_id": manifest.get("build_id"),
        "command": command,
        "database_dir": str(database_path),
        "duration_seconds": elapsed,
        "ended_at": ended_at.isoformat(),
        "graph": graph_name,
        "installed_version": installed_version,
        "package_dir": str(package_root),
        "preflight": "passed",
        "return_code": completed.returncode,
        "started_at": started_at.isoformat(),
        "status": "passed" if completed.returncode == 0 else "failed",
        "stderr_log": stderr_path.name,
        "stdout_log": stdout_path.name,
        "target": manifest.get("target"),
        "version_probe": {
            "return_code": version_probe.returncode,
            "stderr": version_probe.stderr.strip(),
            "stdout": version_probe.stdout.strip(),
        },
    }
    _write_result(results / "import_result.json", result)
    if completed.returncode != 0:
        raise TuGraphLoadError(
            f"lgraph_import failed with exit code {completed.returncode}; "
            f"see {results / 'import_result.json'}"
        )
    return result


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify and load a TuGraph 4.5.2 import package on the server."
    )
    parser.add_argument("--package-dir", required=True, type=Path)
    parser.add_argument("--database-dir", required=True, type=Path)
    parser.add_argument("--result-dir", required=True, type=Path)
    parser.add_argument("--graph", default="sack")
    parser.add_argument("--binary", default="lgraph_import")
    parser.add_argument(
        "--installed-version",
        required=True,
        help=f"Operator-verified TuGraph version; must be {TUGRAPH_TARGET_VERSION}",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main() -> None:
    args = _parse_args()
    result = load_tugraph_package(
        package_dir=args.package_dir,
        database_dir=args.database_dir,
        result_dir=args.result_dir,
        graph_name=args.graph,
        binary=args.binary,
        installed_version=args.installed_version,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
