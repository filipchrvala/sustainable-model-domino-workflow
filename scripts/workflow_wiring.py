"""Shared Domino workflow graph wiring (Predict -> MRK branch)."""

from __future__ import annotations

PREDICT_NODE = "104_520d5908-51bd-5715-b120-38517246b71f"
PREDICT_UPSTREAM = "PredictPie_520d590851bd5715b12038517246b71f"
TECH_LIMITS_NODE = "108_269fe489-9457-5a76-8249-e7c85fa56d5c"
SIZING_NODE = "109_8fe65e2c-787e-5e5a-b185-8aaabfef8014"

LOAD_FROM_PREDICT_NODES = (
    "108_269fe489-9457-5a76-8249-e7c85fa56d5c",  # TechnicalLimits
    "109_8fe65e2c-787e-5e5a-b185-8aaabfef8014",  # SizingOptimization
    "112_68e22997-e9ce-5182-b799-55684e726d06",  # SolarSim
    "113_c6559d37-047b-50fb-81ff-c4c26eee0457",  # BatteryStrategy
    "114_a3931fd4-7104-52b0-bdb2-7043bb88583c",  # BatterySim
    "115_9f734ffd-ed6b-5ddf-a85d-5567300fb901",  # Simulate
)


def wire_predict_output_schema(piece: dict) -> None:
    out = piece.get("output_schema") or {}
    props = out.setdefault("properties", {})
    props["runtime_load_csv"] = {
        "description": "Load CSV for MRK sizing/simulation (from predictions)",
        "title": "Runtime Load Csv",
        "type": "string",
    }
    req = out.setdefault("required", [])
    if "runtime_load_csv" not in req:
        req.append("runtime_load_csv")


def wire_load_csv_from_predict(data: dict) -> None:
    pieces_data = data.get("workflowPiecesData") or {}
    for node_id in LOAD_FROM_PREDICT_NODES:
        node = pieces_data.get(node_id)
        if not node:
            continue
        inputs = node.get("inputs") or {}
        if "load_csv" not in inputs:
            continue
        inputs["load_csv"] = {
            "fromUpstream": True,
            "upstreamId": PREDICT_UPSTREAM,
            "upstreamArgument": "runtime_load_csv",
            "upstreamValue": "PredictPiece (520d5908) - Runtime Load Csv",
            "value": "",
        }


def ensure_predict_before_technical_limits(data: dict) -> None:
    _ensure_edge(data, PREDICT_NODE, TECH_LIMITS_NODE)


def ensure_predict_before_sizing(data: dict) -> None:
    """Domino/Airflow needs a DAG edge to pass Predict XCom to Sizing load_csv."""
    _ensure_edge(data, PREDICT_NODE, SIZING_NODE)


def ensure_predict_before_load_csv_consumers(data: dict) -> None:
    """Airflow only resolves fromUpstream XCom when the upstream task is a DAG ancestor."""
    for node_id in LOAD_FROM_PREDICT_NODES:
        _ensure_edge(data, PREDICT_NODE, node_id)


def _ensure_edge(data: dict, source: str, target: str) -> None:
    edges = data.setdefault("workflowEdges", [])
    if any(e.get("source") == source and e.get("target") == target for e in edges):
        return
    edges.append(
        {
            "source": source,
            "sourceHandle": f"source-{source}",
            "target": target,
            "targetHandle": f"target-{target}",
            "id": f"reactflow__edge-{source}source-{source}-{target}target-{target}",
            "markerEnd": {"type": "arrowclosed", "width": 20, "height": 20},
        }
    )


def apply_production_wiring(data: dict) -> None:
    for piece in data.get("workflowPieces", {}).values():
        if piece.get("name") == "PredictPiece":
            wire_predict_output_schema(piece)
    wire_load_csv_from_predict(data)
    ensure_predict_before_load_csv_consumers(data)
