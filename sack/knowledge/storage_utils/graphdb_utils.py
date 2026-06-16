from datetime import datetime
from glob import glob
import json
import os
import shutil
import time
from urllib.parse import quote

import requests
from tqdm import tqdm

from sack.knowledge.knowledge_config import SACKKnowledgeConfig


def create_graphdb_repo(graphdb_endpoint, graphdb_repo_name):
    url = graphdb_endpoint + "/rest/repositories"
    graphdb_repos = json.loads(requests.get(url).text)
    graphdb_repo_ids = [i["id"] for i in graphdb_repos]
    headers = {"Content-Type": "application/json"}

    if graphdb_repo_name in graphdb_repo_ids:
        if not SACKKnowledgeConfig.replace_existing_graphdb_repo:
            return
        response = requests.delete(f"{graphdb_endpoint}/rest/repositories/{graphdb_repo_name}")
        if response.status_code // 100 != 2:
            print(datetime.now(), "Error deleting GraphDB repo:", graphdb_repo_name, response.text)

    data = {
        "id": graphdb_repo_name,
        "type": "graphdb",
        "title": graphdb_repo_name,
        "params": {
            "defaultNS": {
                "name": "defaultNS",
                "label": "Default namespaces for imports(';' delimited)",
                "value": "",
            },
            "imports": {
                "name": "imports",
                "label": "Imported RDF files(';' delimited)",
                "value": "",
            },
            "enableContextIndex": {
                "name": "enableContextIndex",
                "label": "Enable context index",
                "value": "true",
            },
        },
    }
    response = requests.post(url, headers=headers, data=json.dumps(data))
    if response.status_code // 100 != 2:
        print(datetime.now(), "Error creating GraphDB repo:", graphdb_repo_name, response.text)
    else:
        print(datetime.now(), "Created GraphDB repo:", graphdb_repo_name)


def populate_pipeline_graphs(pipeline_graphs_base_dir, graphdb_endpoint, graphdb_repo):
    default_ttls = [i for i in os.listdir(pipeline_graphs_base_dir) if i.endswith(".ttl")]

    print(datetime.now(), "Uploading default and library graphs...")
    for ttl_file in default_ttls:
        _upload_graph(
            file_path=os.path.join(pipeline_graphs_base_dir, ttl_file),
            graphdb_endpoint=graphdb_endpoint,
            graphdb_repo=graphdb_repo,
        )

    all_files = glob(os.path.join(pipeline_graphs_base_dir, "**", "*.ttl"), recursive=True)
    pipeline_graph_dirs = [i for i in os.listdir(pipeline_graphs_base_dir) if not i.endswith(".ttl")]
    print(datetime.now(), f"Uploading {len(all_files)} pipeline graphs for {len(pipeline_graph_dirs)} datasets...")

    for pipeline_graph_dir in tqdm(pipeline_graph_dirs):
        graph_dir = os.path.join(pipeline_graphs_base_dir, pipeline_graph_dir)
        for pipeline_graph in os.listdir(graph_dir):
            pipeline_graph_path = os.path.join(graph_dir, pipeline_graph)
            if not pipeline_graph_path.endswith(".ttl"):
                continue

            named_graph_uri_raw = None
            with open(pipeline_graph_path, "r", encoding="utf-8") as f:
                for line in f:
                    if "a sack:Statement" in line:
                        named_graph_uri_raw = "/".join(
                            line.split()[0].replace("<http://sack.local/", "").split("/")[:-1]
                        )
                        break

            named_graph_uri = "http://sack.local/" + quote(named_graph_uri_raw or pipeline_graph_dir)
            _upload_graph(
                file_path=pipeline_graph_path,
                graphdb_endpoint=graphdb_endpoint,
                graphdb_repo=graphdb_repo,
                named_graph_uri=named_graph_uri,
            )


def _upload_graph(file_path, graphdb_endpoint, graphdb_repo, named_graph_uri=None):
    headers = {"Content-Type": "application/x-turtle", "Accept": "application/json"}
    with open(file_path, "rb") as f:
        file_content = f.read()

    upload_url = f"{graphdb_endpoint}/repositories/{graphdb_repo}/statements"
    if named_graph_uri:
        upload_url = f"{graphdb_endpoint}/repositories/{graphdb_repo}/rdf-graphs/service?graph={named_graph_uri}"

    response = requests.post(upload_url, headers=headers, data=file_content)
    if response.status_code // 100 != 2:
        print("Error uploading file:", file_path, "Error:", response.text)


def populate_data_global_schema_graph(data_global_schema_graph_path, graphdb_repo_name, graphdb_endpoint, graphdb_import_path):
    tmp_file_name = f"{graphdb_repo_name}_import.ttl"
    dst_path = os.path.join(graphdb_import_path, tmp_file_name)
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    shutil.copy2(data_global_schema_graph_path, dst_path)
    print(f"{datetime.now()} Copied graph file to GraphDB import path: {dst_path}", flush=True)

    url = f"{graphdb_endpoint}/rest/repositories/{graphdb_repo_name}/import/server"
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, headers=headers, data=json.dumps({"fileNames": [tmp_file_name]}))

    if response.status_code != 202:
        print(f"{datetime.now()} GraphDB import request failed: status={response.status_code}, response={response.text}", flush=True)
        return

    print(f"{datetime.now()} Submitted graph file to GraphDB import queue.", flush=True)
    import_completed = False
    while not import_completed:
        time.sleep(5)
        status_response = None
        try:
            status_response = requests.get(url, headers=headers, timeout=10)
            status_response.raise_for_status()
            tasks = status_response.json()
            print(f"[{datetime.now()}] Found {len(tasks)} GraphDB import tasks.", flush=True)

            current_task = next((t for t in tasks if tmp_file_name in t.get("fileNames", [])), None)
            if current_task:
                task_status = current_task.get("status")
                print(f"[{datetime.now()}] Current graph import status: {task_status}", flush=True)
                if task_status in {"FINISHED", "DONE"}:
                    import_completed = True
                elif task_status == "FAILED":
                    print(f"[{datetime.now()}] GraphDB import failed: {current_task.get('error', 'unknown error')}", flush=True)
                    import_completed = True
            elif tasks and tasks[0].get("status") == "DONE":
                import_completed = True
        except Exception as exc:
            response_text = status_response.text if status_response is not None else "no response"
            print(f"[{datetime.now()}] Failed to check GraphDB import status: {exc}; response={response_text}", flush=True)

    if os.path.exists(dst_path):
        os.remove(dst_path)
        print(f"{datetime.now()} Removed temporary graph import file.", flush=True)
