"""Upload UC3.3 workflow seed inputs to OneData (FilipsSpace/inputs/).

Reads local test/catalog files and mirrors them to a stable OneData prefix so
Domino workflow nodes can reference onedata:/// paths instead of shared_storage.

Requires env: ONEDATA_ONEZONE_HOST, ONEDATA_TOKEN
Optional: ONEDATA_INPUT_PREFIX (default onedata:///FilipsSpace/inputs)

Run:  python scripts/upload_onedata_inputs.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "pieces"))

from common import onedata_io as od  # noqa: E402

HOST = os.environ["ONEDATA_ONEZONE_HOST"]
TOKEN = os.environ["ONEDATA_TOKEN"]
PREFIX = os.environ.get("ONEDATA_INPUT_PREFIX", "onedata:///FilipsSpace/inputs").rstrip("/")

SECRETS = {
    "onedata_onezone_host": HOST,
    "onedata_token": TOKEN,
    "onedata_output_dir": PREFIX,
}

TESTS = REPO / "tests"
UPLOADS: list[tuple[Path, str]] = [
    (TESTS / "FetchEnergyDataPiece_Inputs" / "load_seed.csv", "load.csv"),
    (TESTS / "FetchEnergyDataPiece_Inputs" / "load_from_web.csv", "load_from_web.csv"),
    (TESTS / "PredictPiece_Inputs" / "predict_planned_load_halfyear.csv", "predict_planned_load_halfyear.csv"),
    (TESTS / "user_input" / "scenario.yaml", "scenario.yaml"),
    (TESTS / "user_input" / "workflow_user_input.json", "workflow_user_input.json"),
    (TESTS / "sustainable" / "history" / "energy_history.csv", "sustainable/history/energy_history.csv"),
]

# Optional prices: generate minimal OKTE-style file from load timestamps if missing locally.
PRICES_LOCAL = TESTS / "FetchEnergyDataPiece_Inputs" / "prices.csv"


def main() -> None:
    od.configure_onedata(SECRETS)
    print(f"Uploading to {PREFIX}/\n")

    for src, remote_name in UPLOADS:
        if not src.is_file():
            print(f"SKIP missing: {src}")
            continue
        target = f"{PREFIX}/{remote_name}"
        od.write_bytes(target, src.read_bytes())
        print(f"  OK  {remote_name}  ({src.stat().st_size:,} B)")

    if PRICES_LOCAL.is_file():
        target = f"{PREFIX}/prices.csv"
        od.write_bytes(target, PRICES_LOCAL.read_bytes())
        print(f"  OK  prices.csv")
    else:
        import pandas as pd

        load = od.read_csv(f"{PREFIX}/load.csv")
        dt_col = "datetime" if "datetime" in load.columns else load.columns[0]
        prices = load[[dt_col]].drop_duplicates().copy()
        prices["price_eur_per_kwh"] = 0.10
        prices.rename(columns={dt_col: "datetime"}, inplace=True)
        target = f"{PREFIX}/prices.csv"
        od.to_csv(prices, target, index=False)
        print(f"  OK  prices.csv  (generated from load timestamps)")

    # Empty dirs for sustainable ingest drop/archive
    for sub in ("sustainable/company_drop", "sustainable/company_archive", "sustainable/model_registry"):
        marker = f"{PREFIX}/{sub}/.keep"
        od.write_bytes(marker, b"")
        print(f"  OK  {sub}/")

    print(f"\nDone. Use PREFIX={PREFIX} in Domino workflow static inputs.")


if __name__ == "__main__":
    main()
