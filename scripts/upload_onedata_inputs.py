"""Upload UC3.3 workflow seed inputs to OneData (FilipsSpace/inputs/).

Reads local test/catalog files and mirrors them to a stable OneData prefix so
Domino workflow nodes can reference onedata:/// paths instead of shared_storage.

Requires ``ONEDATA_TOKEN`` in the environment (see ``.env.example``).

Run:
  python scripts/generate_weekly_test_data.py
  python scripts/upload_onedata_inputs.py --weekly
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "pieces"))

from common import onedata_io as od  # noqa: E402
from common.onedata_defaults import DEFAULT_ONEZONE_HOST, DEFAULT_OUTPUT_DIR  # noqa: E402

PREFIX = os.environ.get("ONEDATA_INPUT_PREFIX", "onedata:///FilipsSpace/inputs").rstrip("/")
RUN_PREFIX = os.environ.get("ONEDATA_RUN_PREFIX", "onedata:///FilipsSpace/run").rstrip("/")

def _secrets() -> dict[str, str]:
    token = (os.environ.get("ONEDATA_TOKEN") or "").strip()
    if not token:
        raise SystemExit(
            "ONEDATA_TOKEN is required. Export your OneData token or use a .env file "
            "(see .env.example)."
        )
    return {
        "onedata_onezone_host": os.environ.get("ONEDATA_ONEZONE_HOST", DEFAULT_ONEZONE_HOST),
        "onedata_token": token,
        "onedata_output_dir": os.environ.get("ONEDATA_OUTPUT_DIR", DEFAULT_OUTPUT_DIR),
    }

TESTS = REPO / "tests"
WEEKLY = TESTS / "weekly"


def _uploads(weekly: bool) -> list[tuple[Path, str]]:
    base = WEEKLY if weekly else TESTS
    if weekly:
        return [
            (base / "load.csv", "load.csv"),
            (base / "prices.csv", "prices.csv"),
            (base / "predict_planned_load_halfyear.csv", "predict_planned_load_halfyear.csv"),
            (base / "scenario.yaml", "scenario.yaml"),
            (base / "workflow_user_input.json", "workflow_user_input.json"),
            (base / "sustainable" / "history" / "energy_history.csv", "sustainable/history/energy_history.csv"),
        ]
    return [
        (TESTS / "FetchEnergyDataPiece_Inputs" / "load_seed.csv", "load.csv"),
        (TESTS / "FetchEnergyDataPiece_Inputs" / "load_from_web.csv", "load_from_web.csv"),
        (TESTS / "PredictPiece_Inputs" / "predict_planned_load_halfyear.csv", "predict_planned_load_halfyear.csv"),
        (TESTS / "user_input" / "scenario.yaml", "scenario.yaml"),
        (TESTS / "user_input" / "workflow_user_input.json", "workflow_user_input.json"),
        (TESTS / "sustainable" / "history" / "energy_history.csv", "sustainable/history/energy_history.csv"),
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weekly", action="store_true", help="Upload tests/weekly (~7 days) instead of full seed data")
    args = parser.parse_args()

    if args.weekly and not (WEEKLY / "load.csv").is_file():
        print("Missing tests/weekly — run: python scripts/generate_weekly_test_data.py")
        sys.exit(1)

    od.configure_onedata(_secrets(), force=True)
    mode = "weekly (~7 days)" if args.weekly else "full seed"
    print(f"Uploading {mode} to {PREFIX}/\n")

    for src, remote_name in _uploads(args.weekly):
        if not src.is_file():
            print(f"SKIP missing: {src}")
            continue
        target = f"{PREFIX}/{remote_name}"
        od.write_bytes(target, src.read_bytes())
        print(f"  OK  {remote_name}  ({src.stat().st_size:,} B)")

    if not args.weekly:
        prices_local = TESTS / "FetchEnergyDataPiece_Inputs" / "prices.csv"
        if prices_local.is_file():
            target = f"{PREFIX}/prices.csv"
            od.write_bytes(target, prices_local.read_bytes())
            print("  OK  prices.csv")
        elif od.exists(f"{PREFIX}/load.csv"):
            import pandas as pd

            load = od.read_csv(f"{PREFIX}/load.csv")
            dt_col = "datetime" if "datetime" in load.columns else load.columns[0]
            prices = load[[dt_col]].drop_duplicates().copy()
            prices["price_eur_per_kwh"] = 0.10
            prices.rename(columns={dt_col: "datetime"}, inplace=True)
            od.to_csv(prices, f"{PREFIX}/prices.csv", index=False)
            print("  OK  prices.csv  (generated from load timestamps)")

    for sub in ("sustainable/company_drop", "sustainable/company_archive", "sustainable/model_registry"):
        marker = f"{PREFIX}/{sub}/.keep"
        od.write_bytes(marker, b"")
        print(f"  OK  {sub}/")

    od.write_bytes(f"{RUN_PREFIX}/mrk_outputs/.keep", b"")
    print("  OK  run/mrk_outputs/")

    print(f"\nDone. Workflow reads onedata:///FilipsSpace/inputs/…")


if __name__ == "__main__":
    main()
