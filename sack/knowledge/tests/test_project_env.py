"""Configuration loading must precede import-time runtime settings."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from sack.env import load_project_env
from sack.paths import PROJECT_ROOT


def test_missing_env_file_is_optional(tmp_path):
    assert load_project_env(tmp_path / ".env") is False


def test_loads_quoted_credentials_and_utf8(tmp_path, monkeypatch):
    for key in ("SACK_TUGRAPH_PASSWORD", "SACK_TUGRAPH_GRAPH"):
        monkeypatch.delenv(key, raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "SACK_TUGRAPH_PASSWORD='secret # with spaces'\n"
        "SACK_TUGRAPH_GRAPH=案例图\n",
        encoding="utf-8",
    )

    assert load_project_env(env_path) is True
    assert os.environ["SACK_TUGRAPH_PASSWORD"] == "secret # with spaces"
    assert os.environ["SACK_TUGRAPH_GRAPH"] == "案例图"


def test_process_environment_wins_including_empty_values(tmp_path, monkeypatch):
    monkeypatch.setenv("SACK_AGENT_GRAPH_BACKEND", "graphdb")
    monkeypatch.setenv("SACK_TUGRAPH_PASSWORD", "")
    env_path = tmp_path / ".env"
    env_path.write_text(
        "SACK_AGENT_GRAPH_BACKEND=tugraph\n"
        "SACK_TUGRAPH_PASSWORD=file-secret\n",
        encoding="utf-8",
    )

    load_project_env(env_path)

    assert os.environ["SACK_AGENT_GRAPH_BACKEND"] == "graphdb"
    assert os.environ["SACK_TUGRAPH_PASSWORD"] == ""


def test_dotenv_drives_store_configuration(tmp_path, monkeypatch):
    from sack.knowledge.stores.factory import create_agent_graph_store

    values = {
        "SACK_AGENT_GRAPH_BACKEND": "tugraph",
        "SACK_TUGRAPH_BOLT_URL": "bolt://example:7687",
        "SACK_TUGRAPH_GRAPH": "example_graph",
        "SACK_TUGRAPH_USER": "reader",
        "SACK_TUGRAPH_PASSWORD": "example-secret",
    }
    for key in values:
        monkeypatch.delenv(key, raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("\n".join(f"{key}={value}" for key, value in values.items()))
    load_project_env(env_path)
    calls = []

    def client_factory(**kwargs):
        calls.append(kwargs)
        return object()

    create_agent_graph_store(client_factory=client_factory)
    assert calls == [{
        "uri": "bolt://example:7687",
        "graph": "example_graph",
        "user": "reader",
        "password": "example-secret",
    }]
    assert create_agent_graph_store(backend="graphdb") is None


def test_package_import_loads_source_root_env_before_configuration(tmp_path):
    # Copy the real bootstrap/configuration modules into an isolated project,
    # without creating or changing the user's actual .env.
    project = tmp_path / "project"
    package = project / "sack"
    knowledge = package / "knowledge"
    knowledge.mkdir(parents=True)
    for name in ("__init__.py", "env.py", "paths.py"):
        shutil.copy2(PROJECT_ROOT / "sack" / name, package / name)
    shutil.copy2(
        PROJECT_ROOT / "sack/knowledge/knowledge_config.py",
        knowledge / "knowledge_config.py",
    )
    (knowledge / "__init__.py").touch()
    expected_path = str(tmp_path / "expected-profiles")
    (project / ".env").write_text(
        f"SACK_SACK_KNOWLEDGE_PROFILES_OUT_PATH={expected_path}\n",
        encoding="utf-8",
    )
    foreign_cwd = tmp_path / "elsewhere"
    foreign_cwd.mkdir()
    (foreign_cwd / ".env").write_text(
        "SACK_SACK_KNOWLEDGE_PROFILES_OUT_PATH=/wrong-directory\n",
        encoding="utf-8",
    )
    environ = dict(os.environ)
    environ.pop("SACK_SACK_KNOWLEDGE_PROFILES_OUT_PATH", None)
    environ["PYTHONPATH"] = os.pathsep.join(
        [str(project), *[str(Path(p).resolve()) for p in sys.path if p]]
    )
    result = subprocess.run(
        [sys.executable, "-c", "import json; "
         "from sack.knowledge.knowledge_config import SACKKnowledgeConfig; "
         "print(json.dumps(SACKKnowledgeConfig.profiles_out_path))"],
        cwd=foreign_cwd,
        env=environ,
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(result.stdout) == expected_path
