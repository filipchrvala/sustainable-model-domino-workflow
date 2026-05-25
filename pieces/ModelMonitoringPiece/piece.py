from __future__ import annotations

import json
import traceback
from pathlib import Path

import pandas as pd
try:
    from domino.base_piece import BasePiece
except ModuleNotFoundError:
    from local_compat.base_piece import BasePiece

from .models import InputModel, OutputModel


class ModelMonitoringPiece(BasePiece):
    """
    Monitors model quality and data drift on 15-minute predictions.
    """

    def piece_function(self, input_data: InputModel) -> OutputModel:
        log_path = Path(self.results_path) / "model_monitoring.log"
        err_path = Path(self.results_path) / "model_monitoring_error.txt"
        try:
            pred_path = Path(input_data.predictions_csv)
            if not pred_path.is_file():
                raise FileNotFoundError(f"Predictions not found: {pred_path}")

            df = pd.read_csv(pred_path)
            if "datetime" not in df.columns or "prediction_load_kw" not in df.columns:
                raise ValueError("Predictions CSV must contain datetime and prediction_load_kw.")

            df["datetime"] = pd.to_datetime(df["datetime"])
            df["hour"] = df["datetime"].dt.hour
            pred = pd.to_numeric(df["prediction_load_kw"], errors="coerce").fillna(0.0)

            report: dict[str, object] = {
                "rows": int(len(df)),
                "pred_mean_kw": float(pred.mean()) if len(df) else 0.0,
                "pred_std_kw": float(pred.std(ddof=0)) if len(df) else 0.0,
                "pred_p95_kw": float(pred.quantile(0.95)) if len(df) else 0.0,
            }

            daily = (
                df.assign(prediction_load_kw=pred, date=df["datetime"].dt.date)
                .groupby("date", as_index=False)["prediction_load_kw"]
                .sum()
            )
            daily["prediction_mwh"] = daily["prediction_load_kw"] * 0.25 / 1000.0
            daily = daily.drop(columns=["prediction_load_kw"])

            if "load_kw" in df.columns:
                actual = pd.to_numeric(df["load_kw"], errors="coerce")
                mask = actual.notna()
                if mask.any():
                    err = pred[mask] - actual[mask]
                    mae = float(err.abs().mean())
                    rmse = float((err.pow(2).mean()) ** 0.5)
                    denom = actual[mask].replace(0, pd.NA).dropna()
                    mape = float((err[denom.index].abs() / denom).mean() * 100) if len(denom) else None
                    report.update(
                        {
                            "actual_available": True,
                            "mae_kw": mae,
                            "rmse_kw": rmse,
                            "mape_pct": mape,
                        }
                    )
                else:
                    report["actual_available"] = False
            else:
                report["actual_available"] = False

            by_hour = (
                df.assign(prediction_load_kw=pred)
                .groupby("hour", as_index=False)["prediction_load_kw"]
                .mean()
                .sort_values("prediction_load_kw", ascending=False)
                .head(5)
            )
            report["top_consumption_hours"] = [
                {"hour": int(r["hour"]), "avg_pred_kw": round(float(r["prediction_load_kw"]), 2)}
                for _, r in by_hour.iterrows()
            ]

            out_dir = Path(self.results_path)
            out_dir.mkdir(parents=True, exist_ok=True)
            report_path = out_dir / "monitoring_report.json"
            daily_path = out_dir / "monitoring_daily.csv"
            report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            daily.to_csv(daily_path, index=False)

            with open(log_path, "a", encoding="utf-8") as f:
                f.write("[INFO] ModelMonitoringPiece completed\n")
            return OutputModel(
                report_json=str(report_path),
                daily_csv=str(daily_path),
                message="Model monitoring report generated.",
            )
        except Exception:
            err = traceback.format_exc()
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("[ERROR] ModelMonitoringPiece failed\n")
                f.write(err + "\n")
            with open(err_path, "w", encoding="utf-8") as f:
                f.write(err)
            raise
