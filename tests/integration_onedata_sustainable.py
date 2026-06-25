"""OneData routing check for the sustainable branch.

Runs IncrementalTrain -> ForecastHorizon -> AnomalyAlert where the model
registry directory is read+written on OneData (the trickiest case). Proves the
stage_registry / upload_registry round-trip and the filename-based model
resolution work against the live OneData store.

Requires env: ONEDATA_ONEZONE_HOST, ONEDATA_TOKEN, optional ONEDATA_OUTPUT_BASE.
Run:  python tests/integration_onedata_sustainable.py
"""
from __future__ import annotations

import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "pieces"))

from common import onedata_io as od  # noqa: E402

HOST = os.environ["ONEDATA_ONEZONE_HOST"]
TOKEN = os.environ["ONEDATA_TOKEN"]
BASE = os.environ.get("ONEDATA_OUTPUT_BASE", "onedata:///FilipsSpace/run_test")
HISTORY = os.environ.get("ONEDATA_HISTORY", "onedata:///FilipsSpace/load_seed.csv")
REGISTRY = f"{BASE.rstrip('/')}/registry"

SECRETS = {
    "onedata_onezone_host": HOST,
    "onedata_token": TOKEN,
    "onedata_output_dir": BASE,
}

od.configure_onedata(SECRETS)


def run(piece_cls, input_model, name):
    tmp = tempfile.mkdtemp(prefix=f"res_{name}_")
    piece = piece_cls.__new__(piece_cls)
    piece.results_path = tmp
    piece.display_result = None
    out = piece.piece_function(input_model, secrets_data=SECRETS)
    target = f"{BASE.rstrip('/')}/{name}"
    listing = od.listdir(target)
    print(f"[OK] {name}: mirrored {len(listing)} file(s) -> {target}")
    for f in listing:
        print("      -", f.rsplit("/", 1)[-1])
    return out, target


def main():
    from pieces.IncrementalTrainPiece.piece import IncrementalTrainPiece
    from pieces.IncrementalTrainPiece.models import InputModel as TrainIn
    from pieces.ForecastHorizonPiece.piece import ForecastHorizonPiece
    from pieces.ForecastHorizonPiece.models import InputModel as FcIn
    from pieces.AnomalyAlertPiece.piece import AnomalyAlertPiece
    from pieces.AnomalyAlertPiece.models import InputModel as AnIn

    print(f"OneData host={HOST}  base={BASE}")
    print(f"history={HISTORY}  registry={REGISTRY}\n")

    # The sustainable branch expects a history with a price_eur_kwh column (which
    # SustainableIngest normally adds). Prepare one on OneData from the seed load.
    import pandas as pd
    seed = od.read_csv(HISTORY)
    if "price_eur_kwh" not in seed.columns:
        seed["price_eur_kwh"] = 0.1
    history = f"{BASE.rstrip('/')}/history.csv"
    od.to_csv(seed, history, index=False)
    print(f"Prepared history with price_eur_kwh -> {history}\n")

    _, it_dir = run(
        IncrementalTrainPiece,
        TrainIn(history_csv=history, model_registry_dir=REGISTRY),
        "IncrementalTrainPiece",
    )
    print("    registry on OneData:", [p.rsplit('/', 1)[-1] for p in od.listdir(REGISTRY)])
    models_index = f"{it_dir}/models_index.json"

    run(
        ForecastHorizonPiece,
        FcIn(history_csv=history, models_index_json=models_index,
             model_registry_dir=REGISTRY, horizon_hours=6),
        "ForecastHorizonPiece",
    )

    run(
        AnomalyAlertPiece,
        AnIn(history_csv=history, models_index_json=models_index,
             model_registry_dir=REGISTRY),
        "AnomalyAlertPiece",
    )

    print("\nSUSTAINABLE CHAIN PASSED — registry round-trip works through OneData.")


if __name__ == "__main__":
    main()
