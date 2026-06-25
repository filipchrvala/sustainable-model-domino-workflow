"""End-to-end OneData routing check for the main numeric chain.

Runs Fetch -> Preprocess -> Train -> Predict -> ModelMonitoring where EVERY
input is read from OneData and EVERY output is mirrored back to OneData. Proves
that the staging (stage_inputs) + mirroring (mirror_results) wiring works against
the live SPICE OneData store, including parquet, joblib model + shift_profile.json
sibling, and CSV.

Requires env: ONEDATA_ONEZONE_HOST, ONEDATA_TOKEN. Uses ONEDATA_OUTPUT_BASE for
the output location (default onedata:///FilipsSpace/run_test).

Run:  python tests/integration_onedata_chain.py
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
SPACE_INPUT = os.environ.get("ONEDATA_INPUT", "onedata:///FilipsSpace/load_seed.csv")

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
    from pieces.FetchEnergyDataPiece.piece import FetchEnergyDataPiece
    from pieces.FetchEnergyDataPiece.models import InputModel as FetchIn
    from pieces.PreprocessEnergyDataPiece.piece import PreprocessEnergyDataPiece
    from pieces.PreprocessEnergyDataPiece.models import InputModel as PrepIn
    from pieces.TrainModelPiece.piece import TrainModelPiece
    from pieces.TrainModelPiece.models import InputModel as TrainIn
    from pieces.PredictPiece.piece import PredictPiece
    from pieces.PredictPiece.models import InputModel as PredIn
    from pieces.ModelMonitoringPiece.piece import ModelMonitoringPiece
    from pieces.ModelMonitoringPiece.models import InputModel as MonIn

    print(f"OneData host={HOST}  output_base={BASE}")
    print(f"Input load CSV (OneData)={SPACE_INPUT}\n")

    # 1) Fetch: read load CSV from OneData, write merged parquet to OneData
    _, fetch_dir = run(
        FetchEnergyDataPiece,
        FetchIn(load_csv=SPACE_INPUT, prices_csv=""),
        "FetchEnergyDataPiece",
    )
    merged = f"{fetch_dir}/merged_energy_data.parquet"

    # 2) Preprocess: read merged parquet from OneData, write train parquet
    _, prep_dir = run(
        PreprocessEnergyDataPiece,
        PrepIn(input_path=merged),
        "PreprocessEnergyDataPiece",
    )
    train_ds = f"{prep_dir}/train_dataset.parquet"

    # 3) Train: read train parquet, write model.pkl + shift_profile.json
    _, train_dir = run(
        TrainModelPiece,
        TrainIn(data_path=train_ds),
        "TrainModelPiece",
    )
    model = f"{train_dir}/xgboost_model.pkl"

    # 4) Predict: read model (+ sibling shift_profile.json) and data from OneData
    _, pred_dir = run(
        PredictPiece,
        PredIn(model_path=model, data_path=train_ds),
        "PredictPiece",
    )
    preds = f"{pred_dir}/predictions_15min.csv"

    # 5) ModelMonitoring: read predictions from OneData, write report
    run(
        ModelMonitoringPiece,
        MonIn(predictions_csv=preds),
        "ModelMonitoringPiece",
    )

    print("\nALL STEPS PASSED — full chain ran end-to-end through OneData.")


if __name__ == "__main__":
    main()
