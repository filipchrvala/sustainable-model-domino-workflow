from __future__ import annotations

import json
import traceback
from pathlib import Path

import joblib
import pandas as pd
try:
    from domino.base_piece import BasePiece
except ModuleNotFoundError:
    from local_compat.base_piece import BasePiece

from .models import InputModel, OutputModel


def _safe_load_model(model_path_raw: str, registry_root_raw: str):
    root = Path(registry_root_raw).resolve()
    model_path = Path(model_path_raw).resolve()
    try:
        model_path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Model path outside registry root: {model_path}") from exc
    if not model_path.is_file():
        raise FileNotFoundError(f"Model file not found: {model_path}")
    return joblib.load(model_path)


def _features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values("datetime").reset_index(drop=True).copy()
    out["hour"] = out["datetime"].dt.hour
    out["dayofweek"] = out["datetime"].dt.dayofweek
    out["month"] = out["datetime"].dt.month
    out["is_weekend"] = (out["dayofweek"] >= 5).astype(int)
    for lag in (1, 4, 96, 192):
        out[f"lag_{lag}"] = out["load_kw"].shift(lag)
    prev = out["load_kw"].shift(1)
    for w in (4, 16, 96):
        out[f"roll_mean_{w}"] = prev.rolling(w).mean()
        out[f"roll_std_{w}"] = prev.rolling(w).std(ddof=0)
    out["price_eur_kwh"] = pd.to_numeric(out.get("price_eur_kwh"), errors="coerce").interpolate(limit_direction="both")
    out["price_eur_kwh"] = out["price_eur_kwh"].fillna(0.1)
    return out


def _fcols() -> list[str]:
    return [
        "hour",
        "dayofweek",
        "month",
        "is_weekend",
        "lag_1",
        "lag_4",
        "lag_96",
        "lag_192",
        "roll_mean_4",
        "roll_std_4",
        "roll_mean_16",
        "roll_std_16",
        "roll_mean_96",
        "roll_std_96",
        "price_eur_kwh",
    ]


class ForecastHorizonPiece(BasePiece):
    def piece_function(self, input_data: InputModel) -> OutputModel:
        log_path = Path(self.results_path) / "forecast_horizon.log"
        err_path = Path(self.results_path) / "forecast_horizon_error.txt"
        try:
            hist = pd.read_csv(input_data.history_csv, parse_dates=["datetime"])
            models = json.loads(Path(input_data.models_index_json).read_text(encoding="utf-8"))
            rows = []
            for dept, model_path in models.items():
                g = hist[hist["department_id"].astype(str) == str(dept)].sort_values("datetime").reset_index(drop=True)
                if len(g) < 300:
                    continue
                model = _safe_load_model(model_path, input_data.model_registry_dir)
                step_minutes = 15
                last_dt = pd.to_datetime(g["datetime"].iloc[-1])
                steps = max(1, int(round(input_data.horizon_hours * 60 / step_minutes)))
                runtime = g[["datetime", "department_id", "load_kw", "price_eur_kwh"]].copy()
                for i in range(steps):
                    next_dt = last_dt + pd.to_timedelta((i + 1) * step_minutes, unit="m")
                    runtime.loc[len(runtime)] = {
                        "datetime": next_dt,
                        "department_id": dept,
                        "load_kw": float("nan"),
                        "price_eur_kwh": float(runtime["price_eur_kwh"].iloc[-1]),
                    }
                    fx = _features(runtime).iloc[-1]
                    X = pd.DataFrame([{c: fx[c] for c in _fcols()}])
                    pred = float(model.predict(X)[0])
                    runtime.loc[runtime.index[-1], "load_kw"] = max(0.0, pred)
                    rows.append(
                        {
                            "datetime": next_dt,
                            "department_id": str(dept),
                            "prediction_load_kw": max(0.0, pred),
                            "horizon_step": i + 1,
                            "horizon_hours": int(input_data.horizon_hours),
                        }
                    )

            out_dir = Path(self.results_path)
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / "forecast_by_department.csv"
            pd.DataFrame(rows).to_csv(out_path, index=False)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[INFO] forecast_rows={len(rows)}\n")
            return OutputModel(message=f"Forecast completed, rows={len(rows)}", forecast_csv=str(out_path))
        except Exception:
            err = traceback.format_exc()
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("[ERROR] ForecastHorizonPiece failed\n")
                f.write(err + "\n")
            with open(err_path, "w", encoding="utf-8") as f:
                f.write(err)
            raise
