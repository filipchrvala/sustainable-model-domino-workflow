"""Prepare sus_onedata.customization for Domino UI import (not GitLab JSON)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CUSTOM = ROOT / "sus_onedata.customization"
COMPILED = ROOT / ".domino" / "compiled_metadata.json"
CONFIG = ROOT / "config.toml"
OUT_GITLAB = ROOT / "sus_onedata.json"
OUT_SPICE = ROOT / "sus_onedata.spice.customization"

# Domino import schema allows only these top-level keys (see domino-frontend QKt).
DOMINO_TOP_KEYS = frozenset(
    {"workflowPieces", "workflowPiecesData", "workflowNodes", "workflowEdges"}
)

# Must match Domino UI / Airflow task_id prefixes (see run_domino_local_test.py).
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


def _node_id_from_upstream_id(upstream_id: str, node_ids: list[str]) -> str | None:
    if not upstream_id or len(upstream_id) < 32:
        return None
    suffix = upstream_id[-32:]
    for node_id in node_ids:
        if node_id.split("_", 1)[1].replace("-", "") == suffix:
            return node_id
    return None


def _short_label(piece_name: str, node_id: str) -> str:
    return f"{piece_name} ({node_id.split('_', 1)[1][:8]})"


def _arg_label(arg_name: str) -> str:
    if arg_name == "run_id":
        return "Run Id"
    return " ".join(part.capitalize() for part in arg_name.split("_"))


def _edge_dict(source: str, target: str) -> dict:
    return {
        "source": source,
        "sourceHandle": f"source-{source}",
        "target": target,
        "targetHandle": f"target-{target}",
        "id": f"reactflow__edge-{source}source-{source}-{target}target-{target}",
        "markerEnd": {"type": "arrowclosed", "width": 20, "height": 20},
    }


def ensure_upstream_edges(data: dict) -> None:
    """Every fromUpstream input must have a graph edge (Airflow task dependency)."""
    node_pieces = {nid: p["name"] for nid, p in data.get("workflowPieces", {}).items()}
    node_ids = list(node_pieces.keys())
    edges = data.setdefault("workflowEdges", [])
    seen = {(e.get("source"), e.get("target")) for e in edges}
    added = 0
    for tgt_id, wpd in data.get("workflowPiecesData", {}).items():
        for spec in wpd.get("inputs", {}).values():
            if not spec.get("fromUpstream"):
                continue
            src_id = _node_id_from_upstream_id(spec.get("upstreamId", ""), node_ids)
            if not src_id or src_id == tgt_id:
                continue
            pair = (src_id, tgt_id)
            if pair not in seen:
                edges.append(_edge_dict(src_id, tgt_id))
                seen.add(pair)
                added += 1
    if added:
        print(f"Added {added} upstream edges")


def fix_upstream_values(data: dict) -> None:
    """Domino UI requires upstreamValue on every fromUpstream input."""
    node_pieces = {nid: p["name"] for nid, p in data.get("workflowPieces", {}).items()}
    node_ids = list(node_pieces.keys())
    for node_id, wpd in data.get("workflowPiecesData", {}).items():
        for arg, spec in wpd.get("inputs", {}).items():
            if not spec.get("fromUpstream"):
                continue
            src_node = _node_id_from_upstream_id(spec.get("upstreamId", ""), node_ids)
            if not src_node:
                continue
            src_piece = node_pieces[src_node]
            up_arg = spec.get("upstreamArgument") or arg
            spec["upstreamId"] = _upstream_id(src_piece, src_node)
            if not str(spec.get("upstreamValue", "")).strip():
                spec["upstreamValue"] = (
                    f"{_short_label(src_piece, src_node)} - {_arg_label(up_arg)}"
                )


def _version() -> str:
    text = CONFIG.read_text(encoding="utf-8") if CONFIG.is_file() else ""
    match = re.search(r'VERSION\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else "0.1.33"


def _ghcr_image(version: str) -> str:
    return f"ghcr.io/filipchrvala/sustainable-model-domino-workflow:{version}-group0"


def _harbor_image(version: str) -> str:
    registry = "harbor.testbed.spice-platform.eu/partner/uc3"
    name = "industry_sg_vre_sustainable_model"
    if CONFIG.is_file():
        text = CONFIG.read_text(encoding="utf-8")
        m = re.search(r'REGISTRY_NAME\s*=\s*"([^"]+)"', text)
        if m:
            registry = m.group(1)
        m = re.search(r'REPOSITORY_NAME\s*=\s*"([^"]+)"', text)
        if m:
            name = m.group(1)
    return f"{registry}/{name}:{version}-group0"


def _secrets_schema() -> dict:
    sys.path.insert(0, str(ROOT / "pieces"))
    from common.onedata_defaults import (
        DEFAULT_ONEDATA_TOKEN,
        DEFAULT_ONEZONE_HOST,
        DEFAULT_OUTPUT_DIR,
    )

    return {
        "title": "SecretsModel",
        "type": "object",
        "properties": {
            "onedata_onezone_host": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "default": DEFAULT_ONEZONE_HOST,
                "description": "OneData Onezone host (default in code)",
                "title": "Onedata Onezone Host",
            },
            "onedata_token": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "default": DEFAULT_ONEDATA_TOKEN,
                "description": "OneData access token (default in code; Domino secrets optional)",
                "title": "Onedata Token",
            },
            "onedata_output_dir": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "default": DEFAULT_OUTPUT_DIR,
                "description": "Base dir for per-run outputs: <dir>/<run_id>/<PieceName>/",
                "title": "Onedata Output Dir",
            },
        },
    }


def _container_resources(piece_name: str, compiled: dict) -> dict:
    meta = compiled.get(piece_name, {})
    cr = meta.get("container_resources") or {}
    if cr:
        return {
            "requests": cr.get("requests", {"cpu": 100, "memory": 128}),
            "limits": cr.get("limits", {"cpu": 500, "memory": 512}),
            "use_gpu": bool(cr.get("use_gpu", False)),
        }
    return {
        "requests": {"cpu": 100, "memory": 128},
        "limits": {"cpu": 500, "memory": 512},
        "use_gpu": False,
    }


def build_domino_customization(*, image: str | None = None) -> dict:
    data = json.loads(CUSTOM.read_text(encoding="utf-8"))
    compiled = json.loads(COMPILED.read_text(encoding="utf-8")) if COMPILED.is_file() else {}
    version = _version()
    image = image or _ghcr_image(version)
    repo_url = "https://github.com/filipchrvala/sustainable-model-domino-workflow"
    secrets = _secrets_schema()

    for node_id, entry in data.get("workflowPieces", {}).items():
        piece_name = entry.get("name", "")
        meta = compiled.get(piece_name, {})
        entry["source_image"] = image
        entry["repository_url"] = repo_url
        entry["source_url"] = f"{repo_url}/tree/main/pieces/{piece_name}"
        entry["secrets_schema"] = secrets
        if meta.get("description"):
            entry["description"] = meta["description"]
        if meta.get("input_schema"):
            entry["input_schema"] = meta["input_schema"]
            props = entry["input_schema"].get("properties", {})
            props.pop("output_dir", None)
            req = entry["input_schema"].get("required", [])
            entry["input_schema"]["required"] = [n for n in req if n != "output_dir"]
        if meta.get("output_schema"):
            entry["output_schema"] = meta["output_schema"]
        entry["container_resources"] = _container_resources(piece_name, compiled)

        wpd = data.setdefault("workflowPiecesData", {}).setdefault(node_id, {})
        wpd.setdefault("storage", {"storageAccessMode": "Read/Write"})
        cr = entry["container_resources"]["limits"]
        wpd["containerResources"] = {
            "cpu": cr.get("cpu", 500),
            "memory": cr.get("memory", 512),
            "useGpu": False,
        }

        for node in data.get("workflowNodes", []):
            if node.get("id") == node_id:
                node.setdefault("data", {})["name"] = piece_name
                style = node["data"].setdefault("style", {})
                style["module"] = piece_name
                style["label"] = piece_name
                node["data"].setdefault("orientation", "horizontal")

    fix_upstream_values(data)
    ensure_upstream_edges(data)

    # Domino yup schema: strict, no unknown keys at root.
    domino = {k: data[k] for k in DOMINO_TOP_KEYS if k in data}
    return domino


def write_domino(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Wrote {path} ({path.stat().st_size} bytes)")


def main() -> int:
    version = _version()
    domino = build_domino_customization()
    write_domino(CUSTOM, domino)

    gitlab = dict(domino)
    gitlab_payload = {
        **gitlab,
        "source_image": _ghcr_image(version),
    }
    write_domino(OUT_GITLAB, gitlab_payload)

    spice = build_domino_customization(image=_harbor_image(version))
    write_domino(OUT_SPICE, spice)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
