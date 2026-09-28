"""Fail-closed, offline TuGraph 4.5.2 import through a local Docker daemon.

Never starts a database service, changes passwords, or overwrites a database.
The immutable package is copied to a writable workspace for .import_tmp.
Run this module on the Docker host, not against a remote Docker context.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Mapping

from sack.knowledge.migration.load_tugraph import (
    TuGraphLoadError,
    verify_tugraph_package,
)


IMAGE_DIGEST = "sha256:b1b0ecc39a580a7cbdac7b4b7ce35f6a92f0981254d314bc1c0a50ca71d4df0d"
DEFAULT_IMAGE = f"docker.m.daocloud.io/tugraph/tugraph-runtime-centos7@{IMAGE_DIGEST}"


def _new_target(value: str | Path, description: str) -> Path:
    supplied = Path(value).expanduser().absolute()
    if supplied.is_symlink():
        raise TuGraphLoadError(f"Refusing symlink {description}: {supplied}")
    path = supplied.resolve()
    if path in {Path(path.anchor), Path.home().resolve()}:
        raise TuGraphLoadError(f"Unsafe {description}: {path}")
    if path.exists():
        raise TuGraphLoadError(f"{description} already exists; refusing overwrite: {path}")
    if not path.parent.is_dir():
        raise TuGraphLoadError(f"{description} parent must already exist: {path.parent}")
    # Docker --mount syntax uses commas as separators; reject ambiguous paths.
    if "," in str(path):
        raise TuGraphLoadError(f"Comma is not allowed in Docker mount path: {path}")
    return path


def _related(a: Path, b: Path) -> bool:
    return a == b or a in b.parents or b in a.parents


def _inspect_image(docker: str, image: str) -> Mapping[str, Any]:
    if not image or image.startswith("-"):
        raise TuGraphLoadError("Invalid Docker image reference")
    # --context default and empty Docker connection overrides force host-local
    # paths; remote daemons cannot safely consume the validated bind mounts.
    env = dict(os.environ)
    for name in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        env.pop(name, None)
    try:
        checked = subprocess.run(
            [docker, "--context", "default", "image", "inspect", image],
            capture_output=True, text=True, check=False, timeout=30, env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TuGraphLoadError(f"Cannot inspect local Docker image: {exc}") from exc
    if checked.returncode:
        raise TuGraphLoadError("Pinned image is not present in the local Docker daemon")
    try:
        metadata = json.loads(checked.stdout)[0]
        digests = metadata["RepoDigests"]
        if not isinstance(digests, list) or not isinstance(metadata.get("Id"), str):
            raise TypeError("Image metadata must include digest list and image ID")
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise TuGraphLoadError("Invalid docker image inspect response") from exc
    if not any(isinstance(item, str) and item.endswith("@" + IMAGE_DIGEST) for item in digests):
        raise TuGraphLoadError("Docker image digest does not match verified TuGraph 4.5.2")
    if metadata.get("Os") != "linux" or metadata.get("Architecture") != "amd64":
        raise TuGraphLoadError("This pinned Docker import path requires linux/amd64")
    return {"id": metadata["Id"], "digest": IMAGE_DIGEST, "architecture": "amd64"}


def load_tugraph_docker(
    *, package_dir: str | Path, database_dir: str | Path,
    result_dir: str | Path, graph_name: str = "sack_poc",
    image: str = DEFAULT_IMAGE, docker_binary: str = "docker",
    memory: str = "2g", cpus: float = 2.0,
    timeout_seconds: float = 1800, dry_run: bool = False,
) -> Mapping[str, Any]:
    """Validate, reserve fresh directories, and run one offline import container.

    Partial database/workspace/logs remain on failure. A retry must use fresh
    targets. Exit code zero is import completion, not online parity acceptance.
    """
    if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", graph_name) is None:
        raise TuGraphLoadError("Invalid graph_name")
    if re.fullmatch(r"[1-9][0-9]*[mMgG]", memory) is None:
        raise TuGraphLoadError("memory must be a positive integer with m/g suffix")
    if not 0 < cpus <= 128 or not 0 < timeout_seconds <= 86400:
        raise TuGraphLoadError("Invalid CPU limit or import timeout")
    root = Path(package_dir).resolve()
    manifest = verify_tugraph_package(root)
    database = _new_target(database_dir, "database directory")
    results = _new_target(result_dir, "result directory")
    if any(_related(a, b) for a, b in ((root, database), (root, results), (database, results))):
        raise TuGraphLoadError("Package, database and results must be disjoint directories")
    if any(path.is_symlink() for path in root.rglob("*")):
        raise TuGraphLoadError("Docker package may not contain symlinks")
    docker = shutil.which(docker_binary)
    if docker is None:
        raise TuGraphLoadError("Cannot find Docker binary")
    identity = _inspect_image(docker, image)
    work = results / "work"
    container_name = "sack-import-" + uuid.uuid4().hex
    command = [
        docker, "--context", "default", "run", "--rm", "--pull", "never",
        "--name", container_name, "--network", "none",
        "--memory", memory, "--memory-swap", memory, "--cpus", str(cpus),
        "--mount", f"type=bind,src={work},dst=/work",
        "--mount", f"type=bind,src={database},dst=/database",
        "--workdir", "/work", "--entrypoint", "lgraph_import", identity["id"],
        "--online", "false", "--config_file", "import.config.json",
        "--dir", "/database", "--graph", graph_name,
        "--overwrite", "false", "--continue_on_error", "false",
    ]
    report: dict[str, Any] = {
        "build_id": manifest["build_id"], "target": manifest["target"],
        "package_dir": str(root), "database_dir": str(database),
        "result_dir": str(results), "graph": graph_name,
        "image": dict(identity), "command": command, "container": container_name,
        "manifest_sha256": hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest(),
        "preflight": "passed", "dry_run": dry_run,
    }
    if dry_run:
        return report

    results.mkdir(mode=0o700, exist_ok=False)
    # Exclusive reservation before Docker creates a bind mount directory.
    try:
        database.mkdir(mode=0o700, exist_ok=False)
    except OSError as exc:
        report.update(status="failed", error=f"Database reservation failed: {exc}")
        (results / "import_result.json").write_text(json.dumps(report, indent=2) + "\n")
        raise TuGraphLoadError(report["error"]) from exc
    env = dict(os.environ)
    for name in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        env.pop(name, None)
    started = monotonic()
    report["started_at"] = datetime.now(timezone.utc).isoformat()
    report.update(status="failed", return_code=None)
    try:
        shutil.copytree(root, work)
        copied_manifest = verify_tugraph_package(work)
        copied_hash = hashlib.sha256((work / "manifest.json").read_bytes()).hexdigest()
        if copied_manifest != manifest or copied_hash != report["manifest_sha256"]:
            raise TuGraphLoadError("Source package changed during workspace preparation")
        with (results / "lgraph_import.stdout.log").open("w") as stdout, (
            results / "lgraph_import.stderr.log"
        ).open("w") as stderr:
            completed = subprocess.run(
                command, stdout=stdout, stderr=stderr, check=False,
                timeout=timeout_seconds, env=env,
            )
        report["return_code"] = completed.returncode
        if completed.returncode == 0:
            report["status"] = "passed"
        else:
            report["error"] = f"Docker import exited with code {completed.returncode}"
    except subprocess.TimeoutExpired:
        report.update(status="timed_out", error="Import exceeded timeout")
        # Killing docker's client does not stop its container. Only remove
        # this invocation's unique, owned import container; never a service.
        try:
            cleanup = subprocess.run(
                [docker, "--context", "default", "rm", "--force", container_name],
                capture_output=True, text=True, check=False, timeout=30, env=env,
            )
            report["timeout_cleanup"] = {"return_code": cleanup.returncode, "stderr": cleanup.stderr}
        except (OSError, subprocess.TimeoutExpired) as exc:
            report["timeout_cleanup"] = {"error": str(exc)}
    except (OSError, TuGraphLoadError) as exc:
        report["error"] = str(exc)
    finally:
        report["duration_seconds"] = monotonic() - started
        report["ended_at"] = datetime.now(timezone.utc).isoformat()
        report["stdout_log"] = "lgraph_import.stdout.log"
        report["stderr_log"] = "lgraph_import.stderr.log"
        (results / "import_result.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
    if report["status"] != "passed":
        raise TuGraphLoadError(f"Docker import failed; see {results / 'import_result.json'}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", required=True, type=Path)
    parser.add_argument("--database-dir", required=True, type=Path)
    parser.add_argument("--result-dir", required=True, type=Path)
    parser.add_argument("--graph", default="sack_poc")
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--docker-binary", default="docker")
    parser.add_argument("--memory", default="2g")
    parser.add_argument("--cpus", default=2.0, type=float)
    parser.add_argument("--timeout-seconds", default=1800.0, type=float)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = load_tugraph_docker(
        package_dir=args.package_dir, database_dir=args.database_dir, result_dir=args.result_dir,
        graph_name=args.graph, image=args.image, docker_binary=args.docker_binary,
        memory=args.memory, cpus=args.cpus, timeout_seconds=args.timeout_seconds, dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
