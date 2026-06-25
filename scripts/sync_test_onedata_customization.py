"""Update test_sus_onedata.customization for sustainable_model paths and run_id wiring."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CUSTOM = ROOT / "test_sus_onedata.customization"
CONFIG = ROOT / "config.toml"

import sys
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pieces"))

from common.onedata_defaults import (  # noqa: E402
    DEFAULT_INPUT_DIR,
    DEFAULT_ONEDATA_TOKEN,
    DEFAULT_ONEZONE_HOST,
    DEFAULT_OUTPUT_DIR,
)

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

ML_PIECES = {
    "PreprocessEnergyDataPiece",
    "TrainModelPiece",
    "PredictPiece",
    "ModelMonitoringPiece",
    "SustainableIngestPiece",
    "IncrementalTrainPiece",
    "ForecastHorizonPiece",
    "AnomalyAlertPiece",
}

MRK_PIECES = {
    "TechnicalLimitsPiece",
    "SizingOptimizationPiece",
    "CatalogSyncPiece",
    "CatalogRankerPiece",
    "SolarSimPiece",
    "BatteryStrategyOptimizerPiece",
    "BatterySimPiece",
    "SimulatePiece",
    "KPIPiece",
    "InvestmentEvalPiece",
    "DashboardPiece",
    "FeasibilityReportPiece",
}

FETCH_ID = "101_d9d6dabb-53d8-582f-8556-9a70b5fee765"
USER_ID = "106_f58ce081-6094-5445-9349-81d75ab09d42"


def _upstream_id(piece_name: str, node_id: str) -> str:
    prefix = DOMINO_TASK_PREFIX[piece_name]
    uuid = node_id.split("_", 1)[1].replace("-", "")
    return f"{prefix}_{uuid}"


def _node_id_from_upstream_id(upstream_id: str, node_pieces: dict[str, str]) -> str | None:
    if not upstream_id or len(upstream_id) < 32:
        return None
    suffix = upstream_id[-32:]
    for node_id in node_pieces:
        if node_id.split("_", 1)[1].replace("-", "") == suffix:
            return node_id
    return None


def _edge_dict(source: str, target: str) -> dict:
    return {
        "source": source,
        "sourceHandle": f"source-{source}",
        "target": target,
        "targetHandle": f"target-{target}",
        "id": f"reactflow__edge-{source}source-{source}-{target}target-{target}",
        "markerEnd": {"type": "arrowclosed", "width": 20, "height": 20},
    }


def normalize_upstream_ids_and_edges(data: dict, node_pieces: dict[str, str]) -> None:
    wpd = data.setdefault("workflowPiecesData", {})
    for node_id, piece_name in node_pieces.items():
        inputs = wpd.setdefault(node_id, {}).setdefault("inputs", {})
        for spec in inputs.values():
            if not spec.get("fromUpstream"):
                continue
            src_node = _node_id_from_upstream_id(spec.get("upstreamId", ""), node_pieces)
            if not src_node:
                continue
            src_piece = node_pieces[src_node]
            spec["upstreamId"] = _upstream_id(src_piece, src_node)

    edges = data.setdefault("workflowEdges", [])
    seen = {(e.get("source"), e.get("target")) for e in edges}
    for node_id in node_pieces:
        for spec in wpd.get(node_id, {}).get("inputs", {}).values():
            if not spec.get("fromUpstream"):
                continue
            src_node = _node_id_from_upstream_id(spec.get("upstreamId", ""), node_pieces)
            if not src_node or src_node == node_id:
                continue
            pair = (src_node, node_id)
            if pair not in seen:
                edges.append(_edge_dict(src_node, node_id))
                seen.add(pair)


def _version_images() -> tuple[str, str]:
    ver = "0.1.30"
    if CONFIG.is_file():
        m = re.search(r'VERSION\s*=\s*"([^"]+)"', CONFIG.read_text(encoding="utf-8"))
        if m:
            ver = m.group(1)
    gh = f"ghcr.io/filipchrvala/sustainable-model-domino-workflow:{ver}-group0"
    harbor = f"harbor.testbed.spice-platform.eu/partner/uc3/industry_sg_vre_sustainable_model:{ver}-group0"
    return gh, harbor


def _wire_run_id(data: dict, node_pieces: dict[str, str]) -> None:
    wpd = data.setdefault("workflowPiecesData", {})
    for node_id, piece_name in node_pieces.items():
        if piece_name in ("FetchEnergyDataPiece", "UserInputPiece"):
            continue
        inputs = wpd.setdefault(node_id, {}).setdefault("inputs", {})
        if piece_name in ML_PIECES:
            src_node, arg = FETCH_ID, "run_id"
            src_piece = "FetchEnergyDataPiece"
        elif piece_name in MRK_PIECES:
            src_node, arg = USER_ID, "run_id"
            src_piece = "UserInputPiece"
        else:
            continue
        inputs["run_id"] = {
            "fromUpstream": True,
            "upstreamId": _upstream_id(src_piece, src_node),
            "upstreamArgument": arg,
            "upstreamValue": "",
            "value": "",
        }


def main() -> None:
    text = CUSTOM.read_text(encoding="utf-8")
    text = text.replace("onedata:///FilipsSpace/run/mrk_outputs", "")
    text = text.replace("onedata:///FilipsSpace/run", DEFAULT_OUTPUT_DIR)
    text = text.replace("onedata:///FilipsSpace/inputs", DEFAULT_INPUT_DIR)
    data = json.loads(text)

    node_pieces: dict[str, str] = {}
    for node in data.get("workflowNodes", []):
        name = node.get("data", {}).get("name")
        if name:
            node_pieces[node["id"]] = name

    _wire_run_id(data, node_pieces)
    normalize_upstream_ids_and_edges(data, node_pieces)

    gh_img, harbor_img = _version_images()
    for piece in data.get("workflowPieces", {}).values():
        piece["source_image"] = harbor_img
        for key in ("input_schema", "output_schema", "secrets_schema"):
            schema = piece.get(key, {})
            props = schema.get("properties", {})
            if key != "secrets_schema" and "run_id" not in props:
                props["run_id"] = {
                    "default": "",
                    "description": "Workflow run id for OneData per-run output folder",
                    "title": "Run Id",
                    "type": "string",
                }
            if key == "secrets_schema":
                props.setdefault("onedata_onezone_host", {})["default"] = DEFAULT_ONEZONE_HOST
                props.setdefault("onedata_output_dir", {})["default"] = DEFAULT_OUTPUT_DIR
                if "onedata_token" in props:
                    props["onedata_token"]["default"] = DEFAULT_ONEDATA_TOKEN
                    props["onedata_token"]["description"] = (
                        "Onedata access token (default in code; Domino secrets optional)"
                    )
        if piece.get("name") in ("FetchEnergyDataPiece", "UserInputPiece"):
            out_props = piece.get("output_schema", {}).get("properties", {})
            out_props.setdefault("run_id", {
                "default": "",
                "title": "Run Id",
                "type": "string",
            })

    data["source_image"] = gh_img
    CUSTOM.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Updated", CUSTOM)
    print("GH image:", gh_img)
    print("Harbor image:", harbor_img)


if __name__ == "__main__":
    main()
