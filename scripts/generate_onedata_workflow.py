"""Generate Domino workflow customization with OneData static input paths.

Reads test_sus.customization and writes test_sus_onedata.customization where
local /home/shared_storage paths are replaced with onedata:///FilipsSpace/inputs/
image tags bumped to config.toml version, secrets defaults applied, and the
MRK branch wired like local run_workflow.py (Predict -> sizing/simulation).

Run:  python scripts/generate_onedata_workflow.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "test_sus.customization"
DST = REPO / "test_sus_onedata.customization"

PREFIX = "onedata:///FilipsSpace/inputs"
RUN_PREFIX = "onedata:///FilipsSpace/run"


def _read_version() -> str:
    text = (REPO / "config.toml").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.strip().startswith("VERSION"):
            return line.split("=", 1)[1].strip().strip('"')
    return "0.1.15"

# Map old shared_storage paths -> OneData input paths
STATIC_MAP = {
    "/home/shared_storage/sustainable_model/load.csv": f"{PREFIX}/load.csv",
    "/home/shared_storage/sustainable_model/prices.csv": f"{PREFIX}/prices.csv",
    "/home/shared_storage/sustainable_model/scenario.yaml": f"{PREFIX}/scenario.yaml",
    "/home/shared_storage/sustainable_model/web_form_state.json": f"{PREFIX}/web_form_state.json",
    "/home/shared_storage/sustainable_model/predict_planned_load_halfyear.csv": f"{PREFIX}/predict_planned_load_halfyear.csv",
    "/home/shared_storage/sustainable_model/mrk_outputs": f"{RUN_PREFIX}/mrk_outputs",
    "/home/shared_storage/sustainable_model/sustainable/history/energy_history.csv": f"{PREFIX}/sustainable/history/energy_history.csv",
    "/home/shared_storage/sustainable_model/sustainable/company_drop": f"{PREFIX}/sustainable/company_drop",
    "/home/shared_storage/sustainable_model/sustainable/company_archive": f"{PREFIX}/sustainable/company_archive",
    "/home/shared_storage/sustainable_model/sustainable/model_registry": f"{PREFIX}/sustainable/model_registry",
    "/home/shared_storage/load.csv": f"{PREFIX}/load.csv",
    "/home/shared_storage/prices.csv": f"{PREFIX}/prices.csv",
}

SECRETS_SCHEMA = {
    "properties": {
        "onedata_onezone_host": {
            "default": "data.spice-platform.eu",
            "description": "Onedata Onezone host (default applied in code if omitted)",
            "title": "Onedata Onezone Host",
            "type": "string",
        },
        "onedata_token": {
            "default": "",
            "description": "Optional; if empty, piece reads ONEDATA_TOKEN env or /run/secrets/onedata_token",
            "title": "Onedata Token",
            "type": "string",
        },
        "onedata_output_dir": {
            "default": RUN_PREFIX,
            "description": "OneData base dir for mirrored piece outputs",
            "title": "Onedata Output Dir",
            "type": "string",
        },
    },
    "title": "SecretsModel",
    "type": "object",
}

# Domino node / upstream ids (stable in test_sus.customization)
PREDICT_NODE = "104_520d5908-51bd-5715-b120-38517246b71f"
PREDICT_UPSTREAM = "PredictPie_520d590851bd5715b12038517246b71f"
TECH_LIMITS_NODE = "108_269fe489-9457-5a76-8249-e7c85fa56d5c"

# Nodes that must consume predicted load (not raw UserInput load)
LOAD_FROM_PREDICT_NODES = (
    "108_269fe489-9457-5a76-8249-e7c85fa56d5c",  # TechnicalLimits
    "109_8fe65e2c-787e-5e5a-b185-8aaabfef8014",  # SizingOptimization
    "112_68e22997-e9ce-5182-b799-55684e726d06",  # SolarSim
    "113_c6559d37-047b-50fb-81ff-c4c26eee0457",  # BatteryStrategy
    "114_a3931fd4-7104-52b0-bdb2-7043bb88583c",  # BatterySim
    "115_9f734ffd-ed6b-5ddf-a85d-5567300fb901",  # Simulate
)


def _wire_predict_output_schema(piece: dict) -> None:
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


def _wire_load_csv_from_predict(data: dict) -> None:
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


def _ensure_predict_before_technical_limits(data: dict) -> None:
    edges = data.setdefault("workflowEdges", [])
    wanted = (PREDICT_NODE, TECH_LIMITS_NODE)
    if any(e.get("source") == wanted[0] and e.get("target") == wanted[1] for e in edges):
        return
    edges.append(
        {
            "source": PREDICT_NODE,
            "sourceHandle": f"source-{PREDICT_NODE}",
            "target": TECH_LIMITS_NODE,
            "targetHandle": f"target-{TECH_LIMITS_NODE}",
            "id": (
                f"reactflow__edge-{PREDICT_NODE}source-{PREDICT_NODE}-"
                f"{TECH_LIMITS_NODE}target-{TECH_LIMITS_NODE}"
            ),
            "markerEnd": {"type": "arrowclosed", "width": 20, "height": 20},
        }
    )


SIZING_NODE = "109_8fe65e2c-787e-5e5a-b185-8aaabfef8014"

SIZING_CONTAINER_RESOURCES = {
    "requests": {"cpu": 200, "memory": 512},
    "limits": {"cpu": 1000, "memory": 2048},
    "use_gpu": False,
}

SIZING_CONTAINER_RESOURCES_UI = {
    "cpu": 1000,
    "memory": 2048,
    "useGpu": False,
}


def _set_sizing_container_resources(data: dict) -> None:
    """Auto sizing loads SimulatePiece helpers and needs more RAM than default 512MB."""
    for piece in data.get("workflowPieces", {}).values():
        if piece.get("name") == "SizingOptimizationPiece":
            piece["container_resources"] = {
                "requests": {"cpu": 200, "memory": 512},
                "limits": {"cpu": 1000, "memory": 2048},
                "use_gpu": False,
            }
            piece["tags"] = ["MRK", "Sizing"]
    node = (data.get("workflowPiecesData") or {}).get(SIZING_NODE)
    if node is not None:
        node["containerResources"] = dict(SIZING_CONTAINER_RESOURCES_UI)


def _set_rolling_prediction_defaults(data: dict) -> None:
    """Match local run_workflow.py: rolling prediction with bridge rows."""
    for piece in data.get("workflowPieces", {}).values():
        if piece.get("name") != "PredictPiece":
            continue
        props = (piece.get("input_schema") or {}).get("properties") or {}
        if "use_rolling_prediction" in props:
            props["use_rolling_prediction"]["default"] = True

    predict_node = "104_520d5908-51bd-5715-b120-38517246b71f"
    node = (data.get("workflowPiecesData") or {}).get(predict_node) or {}
    spec = (node.get("inputs") or {}).get("use_rolling_prediction")
    if spec is not None:
        spec["value"] = True


def main() -> None:
    version = _read_version()
    data = json.loads(SRC.read_text(encoding="utf-8"))

    for piece in data.get("workflowPieces", {}).values():
        tag = f":{version}-group0"
        if "source_image" in piece:
            piece["source_image"] = re.sub(
                r":[\d.]+-group\d+", tag, piece["source_image"]
            )
        piece["secrets_schema"] = SECRETS_SCHEMA
        if piece.get("name") == "PredictPiece":
            _wire_predict_output_schema(piece)

    for node in data.get("workflowPiecesData", {}).values():
        inputs = node.get("inputs") or {}
        for spec in inputs.values():
            if not spec.get("fromUpstream") and isinstance(spec.get("value"), str):
                val = spec["value"]
                if val in STATIC_MAP:
                    spec["value"] = STATIC_MAP[val]

    _wire_load_csv_from_predict(data)
    _ensure_predict_before_technical_limits(data)
    _set_rolling_prediction_defaults(data)
    _set_sizing_container_resources(data)

    DST.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"Wrote {DST.name}  (images {version}, "
        f"Predict->MRK load wiring, use_rolling_prediction=true, secrets defaults in schema)"
    )


if __name__ == "__main__":
    main()
