"""Register UC3.3 sustainable model, create workflow from customization, run in local Domino."""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
API_BASE = "http://localhost:8000"
WORKSPACE_ID = 1
REPO_PATH = "filipchrvala/sustainable-model-domino-workflow"
REPO_URL = f"https://github.com/{REPO_PATH}"
DEFAULT_CUSTOM = ROOT / "test_sus_onedata.customization"

DOMINO_TASK_PREFIX: dict[str, str] = {
    "FetchEnergyDataPiece": "FetchEnerg",
    "PreprocessEnergyDataPiece": "Preprocess",
    "TrainModelPiece": "TrainModel",
    "PredictPiece": "PredictPie",
    "ModelMonitoringPiece": "ModelMonit",
    "UserInputPiece": "UserInputP",
    "WebUserInputPiece": "WebUserInp",
    "TechnicalLimitsPiece": "TechnicalL",
    "SizingOptimizationPiece": "SizingOpti",
    "CatalogSyncPiece": "CatalogSyn",
    "CatalogRankerPiece": "CatalogRan",
    "SolarSimPiece": "SolarSimPi",
    "BatteryStrategyOptimizerPiece": "BatteryStr",
    "BatterySimPiece": "BatterySim",
    "SimulatePiece": "SimulatePi",
    "KPIPiece": "KPIPiece",
    "InvestmentEvalPiece": "Investment",
    "DashboardPiece": "DashboardP",
    "FeasibilityReportPiece": "Feasibilit",
    "SustainableIngestPiece": "Sustainabl",
    "IncrementalTrainPiece": "Incrementa",
    "ForecastHorizonPiece": "ForecastHo",
    "AnomalyAlertPiece": "AnomalyAle",
}


def _upstream_id(piece_name: str, node_id: str) -> str:
    prefix = DOMINO_TASK_PREFIX[piece_name]
    uuid = node_id.split("_", 1)[1].replace("-", "")
    return f"{prefix}_{uuid}"


def _login() -> str:
    r = requests.post(
        f"{API_BASE}/auth/login",
        json={"email": "admin@email.com", "password": "admin"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _node_uuid(node_id: str) -> str:
    return node_id.split("_", 1)[1].replace("-", "")


def _task_id_for_upstream(upstream_id: str, node_to_task: dict[str, str]) -> str:
    suffix = upstream_id[-32:]
    for node_id, task_id in node_to_task.items():
        if _node_uuid(node_id) == suffix:
            return task_id
    return upstream_id


def _build_node_maps(custom: dict) -> tuple[dict[str, str], dict[str, str]]:
    node_to_task: dict[str, str] = {}
    task_to_node: dict[str, str] = {}
    for node_id, piece in custom.get("workflowPieces", {}).items():
        piece_name = piece["name"]
        task_id = _upstream_id(piece_name, node_id)
        node_to_task[node_id] = task_id
        task_to_node[task_id] = node_id
    return node_to_task, task_to_node


def _input_kwargs(node_id: str, custom: dict, node_to_task: dict[str, str]) -> dict:
    wpd = custom.get("workflowPiecesData", {}).get(node_id, {})
    inputs = wpd.get("inputs", {})
    piece = custom["workflowPieces"][node_id]
    schema_props = piece.get("input_schema", {}).get("properties", {})
    out: dict = {}
    for arg_name in schema_props:
        if arg_name == "output_dir":
            continue
        spec = inputs.get(arg_name, {})
        if spec.get("fromUpstream"):
            upstream_task = _task_id_for_upstream(spec.get("upstreamId", ""), node_to_task)
            out[arg_name] = {
                "fromUpstream": True,
                "upstreamTaskId": upstream_task,
                "upstreamArgument": spec.get("upstreamArgument"),
                "value": "",
            }
        else:
            out[arg_name] = {
                "fromUpstream": False,
                "upstreamTaskId": None,
                "upstreamArgument": None,
                "value": spec.get("value", schema_props[arg_name].get("default", "")),
            }
    return out


def _dependencies(node_id: str, custom: dict, node_to_task: dict[str, str]) -> list[str]:
    deps: list[str] = []
    for edge in custom.get("workflowEdges", []):
        if edge.get("target") == node_id:
            src = edge.get("source")
            if src in node_to_task:
                tid = node_to_task[src]
                if tid not in deps:
                    deps.append(tid)
    wpd = custom.get("workflowPiecesData", {}).get(node_id, {})
    my_task = node_to_task.get(node_id)
    for spec in wpd.get("inputs", {}).values():
        if not spec.get("fromUpstream"):
            continue
        upstream_task = _task_id_for_upstream(spec.get("upstreamId", ""), node_to_task)
        if upstream_task and upstream_task != my_task and upstream_task not in deps:
            deps.append(upstream_task)
    return deps


def customization_to_workflow_request(custom: dict, *, name: str, source_image: str) -> dict:
    node_to_task, _ = _build_node_maps(custom)
    tasks: dict = {}
    for node_id, piece in custom.get("workflowPieces", {}).items():
        task_id = node_to_task[node_id]
        wpd = custom.get("workflowPiecesData", {}).get(node_id, {})
        cr = piece.get("container_resources") or {
            "requests": {"cpu": 100, "memory": 128},
            "limits": {"cpu": 500, "memory": 128},
            "use_gpu": False,
        }
        if wpd.get("containerResources"):
            wcr = wpd["containerResources"]
            cr = {
                "requests": {"cpu": 100, "memory": 128},
                "limits": {"cpu": wcr.get("cpu", 500), "memory": wcr.get("memory", 128)},
                "use_gpu": bool(wcr.get("useGpu", False)),
            }
        tasks[task_id] = {
            "task_id": task_id,
            "piece": {"name": piece["name"], "source_image": source_image},
            "workflow_shared_storage": {
                "source": "None",
                "mode": wpd.get("storage", {}).get("storageAccessMode", "Read/Write"),
                "provider_options": {},
            },
            "container_resources": cr,
            "dependencies": _dependencies(node_id, custom, node_to_task),
            "piece_input_kwargs": _input_kwargs(node_id, custom, node_to_task),
        }
    ui_nodes: dict = {}
    for node in custom.get("workflowNodes", []):
        node_id = node["id"]
        task_id = node_to_task.get(node_id)
        if task_id:
            ui_nodes[task_id] = node
    return {
        "workflow": {
            "name": name,
            "selectStartDate": "now",
            "startDateTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "selectEndDate": "never",
            "endDateTime": None,
            "scheduleInterval": "none",
            "generateReport": False,
            "description": "Automated local Domino UC3.3 OneData test",
        },
        "tasks": tasks,
        "ui_schema": {"nodes": ui_nodes, "edges": custom.get("workflowEdges", [])},
        "forageSchema": custom,
    }


def ensure_piece_repository(token: str, version: str) -> int:
    h = _headers(token)
    repos = requests.get(
        f"{API_BASE}/pieces-repositories",
        params={"workspace_id": WORKSPACE_ID, "page": 0, "page_size": 50},
        headers=h,
        timeout=60,
    )
    repos.raise_for_status()
    for repo in repos.json().get("data", []):
        if repo.get("path") == REPO_PATH:
            print(f"Piece repository id={repo['id']} version={repo.get('version')}")
            return repo["id"]
    body = {
        "workspace_id": WORKSPACE_ID,
        "source": "github",
        "path": REPO_PATH,
        "version": version,
        "url": REPO_URL,
    }
    r = requests.post(f"{API_BASE}/pieces-repositories", json=body, headers=h, timeout=120)
    r.raise_for_status()
    repo_id = r.json()["id"]
    print(f"Registered piece repository id={repo_id} version={version}")
    return repo_id


def piece_source_image(token: str, repo_id: int, piece_name: str = "FetchEnergyDataPiece") -> str:
    h = _headers(token)
    r = requests.get(f"{API_BASE}/pieces-repositories/{repo_id}/pieces", headers=h, timeout=60)
    r.raise_for_status()
    for piece in r.json():
        if piece.get("name") == piece_name:
            return piece["source_image"]
    raise RuntimeError(f"Piece {piece_name} not found in repository {repo_id}")


def create_workflow(token: str, payload: dict) -> int:
    h = _headers(token)
    r = requests.post(
        f"{API_BASE}/workspaces/{WORKSPACE_ID}/workflows",
        json=payload,
        headers=h,
        timeout=120,
    )
    r.raise_for_status()
    wf_id = r.json()["id"]
    print(f"Created workflow id={wf_id} name={payload['workflow']['name']}")
    return wf_id


def trigger_run(token: str, workflow_id: int, *, wait_dag: int = 120) -> None:
    h = _headers(token)
    deadline = time.time() + wait_dag
    while time.time() < deadline:
        r = requests.post(
            f"{API_BASE}/workspaces/{WORKSPACE_ID}/workflows/{workflow_id}/runs",
            headers=h,
            timeout=60,
        )
        if r.status_code == 204:
            print("Triggered workflow run")
            return
        if r.status_code == 409:
            time.sleep(3)
            continue
        r.raise_for_status()
    raise TimeoutError("Workflow DAG not ready in Airflow within timeout")


def latest_run_id(token: str, workflow_id: int) -> str:
    h = _headers(token)
    for _ in range(30):
        r = requests.get(
            f"{API_BASE}/workspaces/{WORKSPACE_ID}/workflows/{workflow_id}/runs",
            params={"page": 0, "page_size": 5},
            headers=h,
            timeout=60,
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        if data:
            return data[0]["workflow_run_id"]
        time.sleep(2)
    raise TimeoutError("No workflow run appeared")


def poll_tasks(token: str, workflow_id: int, run_id: str, *, timeout: int = 7200) -> list[dict]:
    h = _headers(token)
    deadline = time.time() + timeout
    last_line = ""
    while time.time() < deadline:
        r = requests.get(
            f"{API_BASE}/workspaces/{WORKSPACE_ID}/workflows/{workflow_id}/runs/{run_id}/tasks",
            params={"page": 0, "page_size": 50},
            headers=h,
            timeout=60,
        )
        r.raise_for_status()
        tasks = r.json().get("data", [])
        states = {t["task_id"]: t.get("state") or "none" for t in tasks}
        line = " | ".join(f"{tid.split('_')[0]}:{state}" for tid, state in sorted(states.items()))
        if line != last_line:
            print(line, flush=True)
            last_line = line
        if tasks:
            terminal = {"success", "failed", "upstream_failed", "skipped"}
            if all((t.get("state") or "none") in terminal for t in tasks):
                return tasks
        time.sleep(15)
    raise TimeoutError("Workflow did not finish within timeout")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run UC3.3 sustainable model in local Domino")
    parser.add_argument("--customization", type=Path, default=DEFAULT_CUSTOM)
    parser.add_argument("--repo-version", default="0.1.32")
    parser.add_argument("--timeout", type=int, default=7200)
    args = parser.parse_args()

    custom = json.loads(args.customization.read_text(encoding="utf-8"))
    token = _login()
    repo_id = ensure_piece_repository(token, args.repo_version)
    source_image = piece_source_image(token, repo_id)
    print(f"Using Docker image: {source_image}")

    wf_name = f"uc33_onedata_{int(time.time())}"
    payload = customization_to_workflow_request(custom, name=wf_name, source_image=source_image)
    print(f"Tasks in workflow: {len(payload['tasks'])}")

    wf_id = create_workflow(token, payload)
    trigger_run(token, wf_id)
    run_id = latest_run_id(token, wf_id)
    print(f"Run id: {run_id}")

    tasks = poll_tasks(token, wf_id, run_id, timeout=args.timeout)
    failed = [t for t in tasks if t.get("state") not in ("success", "skipped", None)]
    print("\n=== TASK RESULTS ===")
    for t in sorted(tasks, key=lambda x: x["task_id"]):
        print(f"  {t['task_id']}: {t.get('state')}")

    if failed:
        print(f"\nFAILED: {len(failed)} task(s)", file=sys.stderr)
        return 1
    print("\nALL TASKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
