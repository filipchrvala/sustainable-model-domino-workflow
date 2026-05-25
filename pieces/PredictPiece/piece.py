
try:
    from domino.base_piece import BasePiece
except ModuleNotFoundError:
    from local_compat.base_piece import BasePiece
from .models import InputModel, OutputModel

import json
import traceback
import numpy as np
import pandas as pd
from pathlib import Path
import joblib
from datetime import datetime


def _default_shift_profile() -> dict:
    return {"by_dayofweek": {}, "global": {"active_hours": [], "blocks": []}}


def _load_shift_profile(model_path: Path) -> dict:
    p = model_path.with_name("shift_profile.json")
    if not p.is_file():
        return _default_shift_profile()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return _default_shift_profile()


def _shift_features_for_datetimes(dt: pd.Series, profile: dict) -> pd.DataFrame:
    dts = pd.to_datetime(dt)
    day_map = profile.get("by_dayofweek", {})
    glob = profile.get("global", {})
    rows = []
    for ts in dts:
        dow = int(ts.dayofweek)
        hour = int(ts.hour)
        day_info = day_map.get(str(dow)) or glob or {}
        blocks = day_info.get("blocks") or []
        active = 0
        block_idx = 0
        for i, b in enumerate(blocks, start=1):
            start, end = int(b[0]), int(b[1])
            if start <= hour < end:
                active = 1
                block_idx = i
                break
        rows.append(
            {
                "shift_active": active,
                "shift_block_index": block_idx,
                "shift_block_count": int(len(blocks)),
            }
        )
    return pd.DataFrame(rows, index=dt.index)


def _add_load_features(df: pd.DataFrame, target: str) -> pd.DataFrame:
    out = df.copy()
    if "department_id" in out.columns:
        out["department_id"] = out["department_id"].astype(str)
        grouped = out.groupby("department_id", sort=False)[target]
        for lag in (1, 4, 96, 192, 672):
            out[f"lag_{lag}"] = grouped.shift(lag)
        prev = grouped.shift(1)
        out["_prev"] = prev
        for w in (4, 16, 96):
            out[f"roll_mean_{w}"] = out.groupby("department_id", sort=False)["_prev"].transform(
                lambda s: s.rolling(w).mean()
            )
            out[f"roll_std_{w}"] = out.groupby("department_id", sort=False)["_prev"].transform(
                lambda s: s.rolling(w).std(ddof=0)
            )
        out = out.drop(columns=["_prev"])
        return out
    for lag in (1, 4, 96, 192, 672):
        out[f"lag_{lag}"] = out[target].shift(lag)
    prev = out[target].shift(1)
    for w in (4, 16, 96):
        out[f"roll_mean_{w}"] = prev.rolling(w).mean()
        out[f"roll_std_{w}"] = prev.rolling(w).std(ddof=0)
    return out


def _encode_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "department_id" in out.columns:
        out["department_id"] = out["department_id"].astype(str)
        out = pd.get_dummies(out, columns=["department_id"], dtype=float)
    for col in out.columns:
        if pd.api.types.is_bool_dtype(out[col]):
            out[col] = out[col].astype(int)
        elif pd.api.types.is_object_dtype(out[col]) or pd.api.types.is_string_dtype(out[col]):
            out[col] = pd.to_numeric(out[col], errors="raise")
    return out


def _safe_lag(loads: np.ndarray, i: int, lag: int) -> float:
    j = i - lag
    if j >= 0:
        return float(loads[j])
    return float(loads[0])


def _safe_roll(loads: np.ndarray, i: int, w: int) -> tuple[float, float]:
    start = max(0, i - w)
    hist = loads[start:i]
    if hist.size == 0:
        base = float(loads[max(0, i - 1)])
        return base, 0.0
    return float(hist.mean()), float(hist.std(ddof=0))


class PredictPiece(BasePiece):

    def piece_function(self, input_data: InputModel) -> OutputModel:
        results_dir = Path(self.results_path or ".")
        results_dir.mkdir(parents=True, exist_ok=True)
        piece_log = results_dir / "predict.log"
        piece_err = results_dir / "predict_error.txt"
        try:
            print("[INFO] PredictPiece started")
            print(f"[INFO] Model path: {input_data.model_path}")
            print(f"[INFO] Data path: {input_data.data_path}")

            model_path = Path(input_data.model_path)
            data_path = Path(input_data.data_path)

            if not model_path.exists():
                raise FileNotFoundError(f"Model not found: {model_path}")

            if not data_path.exists():
                raise FileNotFoundError(f"Prediction data not found: {data_path}")

            model = joblib.load(model_path)
            shift_profile = _load_shift_profile(model_path)

            if data_path.suffix == ".parquet":
                df = pd.read_parquet(data_path)
            else:
                df = pd.read_csv(data_path)

            if "datetime" not in df.columns:
                print("[WARN] datetime column not found, trying index reset")
                df = df.reset_index()

            if "datetime" not in df.columns:
                raise ValueError(
                    f"Prediction dataset must contain datetime column. "
                    f"Columns found: {df.columns.tolist()}"
                )

            df["datetime"] = pd.to_datetime(df["datetime"])
            if "department_id" in df.columns:
                df["department_id"] = df["department_id"].astype(str)
                df = df.sort_values(["department_id", "datetime"]).reset_index(drop=True)
            else:
                df = df.sort_values("datetime").reset_index(drop=True)

            target = "load_kw"

            if target not in df.columns:
                raise ValueError(
                    f"Prediction dataset must contain '{target}'. "
                    f"Columns: {df.columns.tolist()}"
                )

            use_rolling = getattr(input_data, "use_rolling_prediction", False)
            bridge_rows = int(getattr(input_data, "bridge_rows", 4))

            if use_rolling:
                print(f"[INFO] Rolling prediction (bridge_rows={bridge_rows})")
                df_out = self._predict_rolling(model, df, bridge_rows, shift_profile)
            else:
                print("[INFO] Batch prediction (shift na load_kw)")
                df_out = self._predict_batch(model, df, target, shift_profile)

            output_path = results_dir / "predictions_15min.csv"
            df_out.to_csv(output_path, index=False)

            feature_names = list(model.get_booster().feature_names)
            log_path = results_dir / "prediction_log.txt"
            with open(log_path, "w") as f:
                f.write(f"Prediction time (UTC): {datetime.utcnow()}\n")
                f.write(f"Rows: {len(df_out)}\n")
                f.write(f"Features used: {feature_names}\n")
                f.write(f"Model: {model_path.name}\n")
                f.write(f"use_rolling_prediction: {use_rolling}\n")

            print("[SUCCESS] Prediction finished")
            print(f"[SUCCESS] Predictions saved to {output_path}")

            return OutputModel(
                message="Prediction finished successfully",
                prediction_file_path=str(output_path)
            )
        except Exception:
            err = traceback.format_exc()
            with open(piece_log, "a", encoding="utf-8") as f:
                f.write("[ERROR] PredictPiece failed\n")
                f.write(err + "\n")
            with open(piece_err, "w", encoding="utf-8") as f:
                f.write(err)
            raise

    def _predict_batch(self, model, df: pd.DataFrame, target: str, shift_profile: dict) -> pd.DataFrame:
        df = df.copy()
        df["hour"] = df["datetime"].dt.hour
        df["dayofweek"] = df["datetime"].dt.dayofweek
        df["month"] = df["datetime"].dt.month
        shift_df = _shift_features_for_datetimes(df["datetime"], shift_profile)
        for c in shift_df.columns:
            df[c] = shift_df[c]
        df = _add_load_features(df, target)
        df = df.dropna().reset_index(drop=True)
        feature_names = model.get_booster().feature_names
        X = _encode_feature_frame(df.drop(columns=["datetime", target], errors="ignore")).reindex(
            columns=feature_names,
            fill_value=0.0,
        )
        preds = model.predict(X)
        df_out = df.copy()
        df_out["prediction_load_kw"] = preds
        return df_out

    def _predict_rolling(self, model, df: pd.DataFrame, bridge_rows: int, shift_profile: dict) -> pd.DataFrame:
        if "department_id" in df.columns:
            parts: list[pd.DataFrame] = []
            for _, group in df.groupby("department_id", sort=False):
                parts.append(self._predict_rolling_single(model, group.reset_index(drop=True), bridge_rows, shift_profile))
            return pd.concat(parts, ignore_index=True).sort_values(["department_id", "datetime"]).reset_index(drop=True)
        return self._predict_rolling_single(model, df.reset_index(drop=True), bridge_rows, shift_profile)

    def _predict_rolling_single(self, model, df: pd.DataFrame, bridge_rows: int, shift_profile: dict) -> pd.DataFrame:
        n = len(df)
        if n < bridge_rows:
            raise ValueError(f"Need at least {bridge_rows} rows for bridge; got {n}")

        feature_names = list(model.get_booster().feature_names)
        loads = np.zeros(n, dtype=float)

        for i in range(bridge_rows):
            v = df.iloc[i, df.columns.get_loc("load_kw")]
            if pd.isna(v):
                raise ValueError(f"Row {i}: load_kw required for bridge (rolling mode)")
            loads[i] = float(v)

        df_out = df.copy()
        df_out["hour"] = df_out["datetime"].dt.hour
        df_out["dayofweek"] = df_out["datetime"].dt.dayofweek
        df_out["month"] = df_out["datetime"].dt.month
        shift_df = _shift_features_for_datetimes(df_out["datetime"], shift_profile)
        for c in shift_df.columns:
            df_out[c] = shift_df[c]

        for i in range(bridge_rows, n):
            lag_1 = loads[i - 1]
            lag_4 = loads[i - 4]
            row = {
                "hour": int(df_out.iloc[i]["hour"]),
                "dayofweek": int(df_out.iloc[i]["dayofweek"]),
                "month": int(df_out.iloc[i]["month"]),
                "lag_1": lag_1,
                "lag_4": lag_4,
            }
            for lag in (96, 192, 672):
                key = f"lag_{lag}"
                if key in feature_names:
                    row[key] = _safe_lag(loads, i, lag)
            for w in (4, 16, 96):
                m_key = f"roll_mean_{w}"
                s_key = f"roll_std_{w}"
                if m_key in feature_names or s_key in feature_names:
                    m, s = _safe_roll(loads, i, w)
                    if m_key in feature_names:
                        row[m_key] = m
                    if s_key in feature_names:
                        row[s_key] = s
            for c in ("shift_active", "shift_block_index", "shift_block_count"):
                if c in feature_names:
                    row[c] = float(df_out.iloc[i][c])
            if "price_eur_kwh" in feature_names:
                if "price_eur_kwh" in df.columns:
                    row["price_eur_kwh"] = float(df.iloc[i]["price_eur_kwh"])
                elif "price_eur_mwh" in df.columns:
                    row["price_eur_kwh"] = float(df.iloc[i]["price_eur_mwh"]) / 1000.0
                else:
                    raise ValueError("Missing price_eur_kwh or price_eur_mwh")
            if "price_eur_per_kwh" in feature_names:
                if "price_eur_per_kwh" in df.columns:
                    row["price_eur_per_kwh"] = float(df.iloc[i]["price_eur_per_kwh"])
                elif "price_eur_kwh" in df.columns:
                    row["price_eur_per_kwh"] = float(df.iloc[i]["price_eur_kwh"])
                elif "price_eur_mwh" in df.columns:
                    row["price_eur_per_kwh"] = float(df.iloc[i]["price_eur_mwh"]) / 1000.0
                else:
                    raise ValueError("Missing price_eur_per_kwh or compatible price column")
            if "department_id" in df_out.columns:
                row["department_id"] = str(df_out.iloc[i]["department_id"])

            X_row = _encode_feature_frame(pd.DataFrame([row])).reindex(columns=feature_names, fill_value=0.0)
            pr = float(model.predict(X_row)[0])
            loads[i] = pr

        df_out["prediction_load_kw"] = loads
        return df_out
