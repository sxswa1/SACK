"""Read-only HTTP acceptance probe with independent SDK clients, not client UI automation."""

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Implementation


async def verify(args):
    tokens = json.loads(Path(args.token_file).read_text())
    if len(tokens) < 2:
        raise ValueError("Provide two independent client tokens for the concurrency probe.")
    async with httpx.AsyncClient(trust_env=False) as client:
        missing = await client.post(args.url, json={})
        wrong = await client.post(args.url, headers={"Authorization": "Bearer invalid"}, json={})
    assert missing.status_code == wrong.status_code == 401

    async def query(label, token):
        async with httpx.AsyncClient(headers={"Authorization": "Bearer " + token}, trust_env=False) as http:
            async with streamable_http_client(args.url, http_client=http) as (read, write, _):
                async with ClientSession(read, write, client_info=Implementation(name=label + "-sdk-probe", version="1")) as session:
                    await session.initialize()
                    tools = (await session.list_tools()).tools
                    assert {t.name for t in tools} == {"list_experiments", "get_experiment_status", "get_experiment_report"}
                    arguments = dict(experiment_name=args.experiment, max_chars=50000)
                    if args.run_id:
                        arguments["run_id"] = args.run_id
                    text = ""
                    while True:
                        result = await session.call_tool("get_experiment_report", arguments)
                        assert not result.isError, result.content
                        value = result.structuredContent
                        text += value["content"]
                        arguments.update(run_id=value["run_id"], offset=value["next_offset"])
                        if value["next_offset"] is None:
                            break
                    sha = hashlib.sha256(text.encode()).hexdigest()
                    assert sha == value["report_sha256"]
                    if args.expected_sha256:
                        assert sha == args.expected_sha256
                    return dict(client=label, run_id=value["run_id"], sha256=sha, chars=len(text),
                                tools=len(tools), status=value["status"])

    clients = await asyncio.gather(*(query(label, token) for label, token in tokens.items()))
    assert len({c["sha256"] for c in clients}) == 1
    return dict(passed=True, transport="streamable-http", client_type="official-sdk-probe",
                unauthorized_status=missing.status_code, invalid_token_status=wrong.status_code, clients=clients)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765/mcp")
    parser.add_argument("--token-file", default=os.environ.get("SACK_MCP_TOKEN_FILE"), required=not os.environ.get("SACK_MCP_TOKEN_FILE"))
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--expected-sha256")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(verify(args)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
