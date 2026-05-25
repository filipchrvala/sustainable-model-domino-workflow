from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pieces.PredictPiece.models import InputModel as PredictInput
from pieces.PredictPiece.piece import PredictPiece
from pieces.TrainModelPiece.models import InputModel as TrainInput
from pieces.TrainModelPiece.piece import TrainModelPiece
from pieces.UserInputPiece.models import InputModel as UserInput
from pieces.UserInputPiece.piece import UserInputPiece


def test_user_input_piece_finds_workflow_json_next_to_inputs(tmp_path: Path) -> None:
    base = tmp_path / "shared"
    base.mkdir()
    load_csv = base / "load.csv"
    prices_csv = base / "prices.csv"
    scenario_yaml = base / "scenario.yaml"
    workflow_json = base / "workflow_user_input.json"

    load_csv.write_text(
        "\n".join(
            [
                "datetime,load_kw",
                "2025-01-01 00:00:00,10",
                "2025-01-01 00:15:00,11",
                "2025-01-01 00:30:00,12",
                "2025-01-01 00:45:00,13",
            ]
        ),
        encoding="utf-8",
    )
    prices_csv.write_text(
        "\n".join(
            [
                "datetime,price_eur_per_kwh",
                "2025-01-01 00:00:00,0.10",
                "2025-01-01 00:15:00,0.11",
                "2025-01-01 00:30:00,0.12",
                "2025-01-01 00:45:00,0.13",
            ]
        ),
        encoding="utf-8",
    )
    scenario_yaml.write_text("timestep_minutes: 15\nproduction:\n  gap_repair_enabled: true\n", encoding="utf-8")
    workflow_json.write_text('{"format":"workflow_user_input_v1"}', encoding="utf-8")

    piece = UserInputPiece.__new__(UserInputPiece)
    piece.results_path = str(tmp_path / "out")
    out = piece.piece_function(
        UserInput(load_csv=str(load_csv), prices_csv=str(prices_csv), scenario_yaml=str(scenario_yaml))
    )

    copied = Path(out.workflow_user_input_json)
    assert copied.is_file()
    assert json.loads(copied.read_text(encoding="utf-8"))["format"] == "workflow_user_input_v1"


def test_train_and_predict_support_multi_department_inputs(tmp_path: Path) -> None:
    datetimes = pd.date_range("2025-01-01 00:00:00", periods=800, freq="15min")
    rows: list[dict[str, float | str]] = []
    for dept, offset in (("A", 20.0), ("B", 55.0)):
        for idx, ts in enumerate(datetimes):
            daily_wave = 8.0 * np.sin(2.0 * np.pi * (idx % 96) / 96.0)
            weekly_wave = 3.0 * np.cos(2.0 * np.pi * (idx % (96 * 7)) / (96 * 7))
            rows.append(
                {
                    "datetime": ts,
                    "department_id": dept,
                    "load_kw": offset + daily_wave + weekly_wave,
                    "price_eur_per_kwh": 0.08 + 0.01 * ((idx % 96) / 96.0),
                }
            )
    train_df = pd.DataFrame(rows)
    train_path = tmp_path / "train_dataset.parquet"
    train_df.to_parquet(train_path, index=False)

    train_piece = TrainModelPiece.__new__(TrainModelPiece)
    train_piece.results_path = str(tmp_path / "train")
    train_out = train_piece.piece_function(TrainInput(data_path=str(train_path)))
    model_path = Path(train_out.model_file_path)
    assert model_path.is_file()

    predict_df = train_df.groupby("department_id", group_keys=False).tail(64).reset_index(drop=True)
    predict_path = tmp_path / "predict.csv"
    predict_df.to_csv(predict_path, index=False)

    predict_piece = PredictPiece.__new__(PredictPiece)
    predict_piece.results_path = str(tmp_path / "predict")
    predict_out = predict_piece.piece_function(
        PredictInput(model_path=str(model_path), data_path=str(predict_path), use_rolling_prediction=True, bridge_rows=4)
    )

    pred_df = pd.read_csv(predict_out.prediction_file_path)
    assert "prediction_load_kw" in pred_df.columns
    assert "department_id" in pred_df.columns
    assert set(pred_df["department_id"]) == {"A", "B"}
    assert pred_df["prediction_load_kw"].notna().all()
