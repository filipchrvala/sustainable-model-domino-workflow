"""Generate Domino workflow customization with OneData static input paths.

Reads test_sus.customization and writes test_sus_onedata.customization where
local /home/shared_storage paths are replaced with onedata:///FilipsSpace/inputs/
and image tags bumped to the current config.toml version.

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
IMAGE_VERSION = "0.1.10"

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
            "description": "Onedata Onezone host",
            "title": "Onedata Onezone Host",
            "type": "string",
        },
        "onedata_token": {
            "description": "Onedata access token (set in Domino workflow secrets)",
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


def main() -> None:
    data = json.loads(SRC.read_text(encoding="utf-8"))

    for piece in data.get("workflowPieces", {}).values():
        tag = f":{IMAGE_VERSION}-group0"
        if "source_image" in piece:
            piece["source_image"] = re.sub(
                r":[\d.]+-group\d+", tag, piece["source_image"]
            )
        piece["secrets_schema"] = SECRETS_SCHEMA

    for node in data.get("workflowPiecesData", {}).values():
        inputs = node.get("inputs") or {}
        for spec in inputs.values():
            if not spec.get("fromUpstream") and isinstance(spec.get("value"), str):
                val = spec["value"]
                if val in STATIC_MAP:
                    spec["value"] = STATIC_MAP[val]

    DST.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {DST.name}  (images {IMAGE_VERSION}, inputs under {PREFIX})")


if __name__ == "__main__":
    main()
