"""Exercise actual SDK transports, including independent concurrent HTTP clients."""

import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Implementation

from sack.mcp.server import load_tokens
from sack.reporting import ReportStore, save_research_report, tracked_run

ROOT = Path(__file__).parents[1]
TOKENS = {"workbuddy": "workbuddy-test-" + "a" * 32, "codex": "codex-test-" + "b" * 32}


@pytest.fixture
def service_env(tmp_path):
    workspace = tmp_path / "experiments/titanic"
    workspace.mkdir(parents=True)
    store = ReportStore(tmp_path / "reports")
    with tracked_run("titanic", workspace, store.root) as run_id:
        save_research_report(workspace, "# 最终报告\n" + "真实归档内容。" * 100)
    tokens = tmp_path / "tokens.json"
    tokens.write_text(json.dumps(TOKENS))
    # Keep developer/deployment secrets out of subprocesses and pytest fixture reprs.
    environment = {key: os.environ[key] for key in ("PATH", "TMPDIR", "LANG", "LC_ALL", "SYSTEMROOT") if key in os.environ}
    return {**environment, "PYTHONPATH": str(ROOT), "SACK_REPORT_ROOT": str(store.root),
            "SACK_MCP_TOKEN_FILE": str(tokens), "SACK_EXPERIMENT_ROOT": str(workspace.parent)}, store, run_id


@pytest.fixture
def http_service(service_env, tmp_path):
    env, store, run_id = service_env
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}/mcp"
    log = (tmp_path / "server.log").open("w+")
    process = subprocess.Popen([sys.executable, "-m", "sack.mcp", "--port", str(port)],
                               cwd=ROOT, env=env, stdout=log, stderr=log)
    try:
        for _ in range(100):
            if process.poll() is not None:
                log.seek(0)
                pytest.fail(log.read())
            try:
                if httpx.get(url, timeout=0.3, trust_env=False).status_code == 401:
                    break
            except httpx.TransportError:
                time.sleep(0.05)
        else:
            pytest.fail("HTTP service did not start")
        yield url, store, run_id
    finally:
        process.terminate()
        process.wait(timeout=10)
        log.close()


def test_http_rejects_missing_wrong_token_and_untrusted_host_origin(http_service):
    url, _, _ = http_service
    assert httpx.post(url, json={}, trust_env=False).status_code == 401
    assert httpx.post(url, headers={"Authorization": "Bearer wrong"}, json={}, trust_env=False).status_code == 401
    headers = {"Authorization": "Bearer " + TOKENS["codex"], "Origin": "https://evil.example"}
    assert httpx.post(url, headers=headers, json={}, trust_env=False).status_code == 403
    headers = {"Authorization": "Bearer " + TOKENS["codex"], "Host": "evil.example"}
    assert httpx.post(url, headers=headers, json={}, trust_env=False).status_code in {400, 421}


async def check_session(session, expected):
    await session.initialize()
    tools = (await session.list_tools()).tools
    assert {t.name for t in tools} == {"list_experiments", "get_experiment_status", "get_experiment_report"}
    assert all(t.annotations.readOnlyHint for t in tools)
    found = await session.call_tool("list_experiments", {"keyword": "titan"})
    assert found.structuredContent["experiments"][0]["run_id"] == expected
    status = await session.call_tool("get_experiment_status", {"experiment_name": "titanic"})
    assert status.structuredContent["status"] == "succeeded"
    first = await session.call_tool("get_experiment_report", {"experiment_name": "titanic", "max_chars": 17})
    assert not first.isError and first.structuredContent["run_id"] == expected
    assert json.loads(first.content[0].text) == first.structuredContent
    second = await session.call_tool("get_experiment_report", {"experiment_name": "titanic", "run_id": expected,
                                                             "offset": first.structuredContent["next_offset"]})
    content = first.structuredContent["content"] + second.structuredContent["content"]
    error = await session.call_tool("get_experiment_report", {"experiment_name": "../private"})
    assert error.isError and error.structuredContent["error"]["code"] == "INVALID_ARGUMENT"
    bad_page = await session.call_tool("get_experiment_report", {"experiment_name": "titanic", "max_chars": 50001})
    assert bad_page.isError
    return content


def test_two_independent_clients_can_query_concurrently(http_service):
    url, store, run_id = http_service
    async def client(label):
        async with httpx.AsyncClient(headers={"Authorization": "Bearer " + TOKENS[label]}, trust_env=False) as http:
            async with streamable_http_client(url, http_client=http) as (read, write, _):
                async with ClientSession(read, write, client_info=Implementation(name=label + "-compatibility-test", version="1")) as session:
                    return await check_session(session, run_id)
    async def both():
        return await asyncio.gather(client("workbuddy"), client("codex"))
    results = asyncio.run(both())
    assert results == [store.get_report("titanic")["content"]] * 2


def test_stdio_protocol_works_without_ml_dependencies(service_env):
    env, store, run_id = service_env
    async def main():
        params = StdioServerParameters(command=sys.executable, args=["-m", "sack.mcp", "--transport", "stdio"],
                                       cwd=str(ROOT), env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                return await check_session(session, run_id)
    assert asyncio.run(main()) == store.get_report("titanic")["content"]


def test_token_configuration_fails_closed(monkeypatch, tmp_path):
    monkeypatch.delenv("SACK_MCP_TOKEN_FILE", raising=False)
    monkeypatch.delenv("SACK_MCP_TOKEN", raising=False)
    with pytest.raises(ValueError):
        load_tokens()
    path = tmp_path / "tokens.json"
    monkeypatch.setenv("SACK_MCP_TOKEN_FILE", str(path))
    for value in [{"a": "short"}, {"a": "x" * 30, "b": "x" * 30}, [], {"a\nb": "x" * 30}]:
        path.write_text(json.dumps(value))
        with pytest.raises(ValueError):
            load_tokens()


def test_service_imports_no_model_or_database_modules():
    result = subprocess.run([sys.executable, "-c", "from sack.mcp.server import create_server; import sys; "
                             "create_server(); assert not any(m in sys.modules for m in "
                             "['sack.sop', 'sack.state', 'sack.Agents', 'torch', 'pandas', 'psycopg', 'openai'])"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
