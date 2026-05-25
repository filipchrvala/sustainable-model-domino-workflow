from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import yaml
from xgboost import XGBRegressor


def _log(log_path: Path, message: str) -> None:
    print(message)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(message + "\n")


def _read_csv_any(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=None, engine="python")
    if len(df.columns) == 1 and ";" in str(df.columns[0]):
        df = pd.read_csv(path, sep=";")
    return df


def _pick_datetime_column(df: pd.DataFrame) -> str | None:
    aliases = {"datetime", "date time", "date_time", "timestamp", "time"}
    for c in df.columns:
        norm = str(c).replace("\ufeff", "").strip().lower()
        if norm in aliases:
            return c
    return None


def _to_numeric_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(",", ".", regex=False), errors="coerce")


def _normalize_source(path: Path, default_department: str) -> pd.DataFrame:
    raw = _read_csv_any(path)
    dt_col = _pick_datetime_column(raw)
    if dt_col is None:
        raise ValueError(f"{path.name}: missing datetime column")

    df = raw.copy()
    dt_raw = df[dt_col].astype(str).str.strip()
    dt = pd.to_datetime(dt_raw, format="%d.%m.%y %H:%M", errors="coerce")
    if dt.isna().all():
        dt = pd.to_datetime(dt_raw, dayfirst=True, errors="coerce")
    df["datetime"] = dt
    df = df.dropna(subset=["datetime"])
    if dt_col != "datetime":
        df = df.drop(columns=[dt_col])

    if "load_kw" in df.columns:
        out = pd.DataFrame(
            {
                "datetime": pd.to_datetime(df["datetime"]),
                "department_id": df.get("department_id", default_department).astype(str),
                "load_kw": _to_numeric_series(df["load_kw"]).fillna(0.0),
            }
        )
    else:
        reserved = {"department_id", "price_eur_kwh", "price_eur_mwh"}
        value_cols = [c for c in df.columns if c not in reserved]
        if not value_cols:
            raise ValueError(f"{path.name}: no load columns found")
        out = df.melt(
            id_vars=["datetime"],
            value_vars=value_cols,
            var_name="department_id",
            value_name="load_kw",
        )
        out["department_id"] = out["department_id"].astype(str).str.strip()
        out["load_kw"] = _to_numeric_series(out["load_kw"]).fillna(0.0)

    if "price_eur_kwh" in df.columns:
        out["price_eur_kwh"] = _to_numeric_series(df["price_eur_kwh"]).fillna(method="ffill").fillna(method="bfill")
    elif "price_eur_mwh" in df.columns:
        out["price_eur_kwh"] = (
            _to_numeric_series(df["price_eur_mwh"]).fillna(method="ffill").fillna(method="bfill") / 1000.0
        )
    return out


def _load_history_csv(path: Path, bootstrap_parquet: Path | None = None) -> pd.DataFrame:
    if not path.is_file():
        if bootstrap_parquet and bootstrap_parquet.is_file():
            dfp = pd.read_parquet(bootstrap_parquet)
            if "datetime" not in dfp.columns or "load_kw" not in dfp.columns:
                raise ValueError(f"bootstrap parquet missing datetime/load_kw: {bootstrap_parquet}")
            if "department_id" not in dfp.columns:
                dfp["department_id"] = "default"
            if "price_eur_kwh" not in dfp.columns:
                if "price_eur_mwh" in dfp.columns:
                    dfp["price_eur_kwh"] = pd.to_numeric(dfp["price_eur_mwh"], errors="coerce") / 1000.0
                else:
                    dfp["price_eur_kwh"] = 0.1
            return dfp[["datetime", "department_id", "load_kw", "price_eur_kwh"]].copy()
        return pd.DataFrame(columns=["datetime", "department_id", "load_kw", "price_eur_kwh"])
    df = pd.read_csv(path, parse_dates=["datetime"])
    for col in ("department_id", "load_kw"):
        if col not in df.columns:
            raise ValueError(f"history file missing '{col}' column: {path}")
    if "price_eur_kwh" not in df.columns:
        df["price_eur_kwh"] = np.nan
    return df


def _time_grid_mins(df: pd.DataFrame, default_minutes: int = 15) -> int:
    if len(df) < 3:
        return default_minutes
    sec = df.sort_values("datetime")["datetime"].diff().dropna().dt.total_seconds()
    if sec.empty:
        return default_minutes
    med = int(max(default_minutes * 60, round(float(sec.median()))))
    return max(1, med // 60)


def _featureize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out = out.sort_values("datetime").reset_index(drop=True)
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
    if "price_eur_kwh" not in out.columns:
        out["price_eur_kwh"] = np.nan
    out["price_eur_kwh"] = pd.to_numeric(out["price_eur_kwh"], errors="coerce").interpolate(limit_direction="both")
    out["price_eur_kwh"] = out["price_eur_kwh"].fillna(0.1)
    return out


def _feature_cols() -> list[str]:
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


@dataclass
class TrainResult:
    department_id: str
    model_path: Path
    rows_used: int
    mode: str


def _train_or_incremental(
    dept: str,
    dept_df: pd.DataFrame,
    model_registry_dir: Path,
    params: dict[str, Any],
    log_path: Path,
) -> TrainResult:
    model_registry_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_registry_dir / f"{dept}_xgb.pkl"

    work = _featureize(dept_df).dropna().reset_index(drop=True)
    if work.empty:
        raise ValueError(f"{dept}: no rows after feature generation")
    feat = _feature_cols()
    X = work[feat]
    y = work["load_kw"].astype(float)

    if model_path.is_file():
        model = joblib.load(model_path)
        model.fit(X, y, xgb_model=model.get_booster(), verbose=False)
        mode = "incremental_update"
    else:
        model = XGBRegressor(
            objective="reg:squarederror",
            learning_rate=float(params.get("learning_rate", 0.03)),
            max_depth=int(params.get("max_depth", 7)),
            n_estimators=int(params.get("n_estimators", 500)),
            subsample=float(params.get("subsample", 0.85)),
            colsample_bytree=float(params.get("colsample_bytree", 0.85)),
            min_child_weight=float(params.get("min_child_weight", 3)),
            reg_alpha=float(params.get("reg_alpha", 0.05)),
            reg_lambda=float(params.get("reg_lambda", 1.5)),
        )
        model.fit(X, y, verbose=False)
        mode = "initial_train"

    joblib.dump(model, model_path)
    _log(log_path, f"[TRAIN] {dept}: {mode}, rows={len(work)}, model={model_path.name}")
    return TrainResult(department_id=dept, model_path=model_path, rows_used=len(work), mode=mode)


def _forecast_horizon(
    model: XGBRegressor,
    dept_df: pd.DataFrame,
    horizon_hours: int,
    step_minutes: int,
) -> pd.DataFrame:
    hist = dept_df.sort_values("datetime").reset_index(drop=True).copy()
    if len(hist) < 250:
        raise ValueError("need at least 250 rows for stable rolling horizon forecast")

    last_dt = pd.to_datetime(hist["datetime"].iloc[-1])
    steps = max(1, int(round(horizon_hours * 60 / step_minutes)))
    freq = f"{step_minutes}min"

    generated_rows: list[dict[str, Any]] = []
    for i in range(steps):
        next_dt = last_dt + pd.to_timedelta((i + 1) * step_minutes, unit="m")
        row = {"datetime": next_dt, "load_kw": np.nan, "price_eur_kwh": float(hist["price_eur_kwh"].iloc[-1])}
        hist = pd.concat([hist, pd.DataFrame([row])], ignore_index=True)
        fx = _featureize(hist).iloc[-1]
        X_row = pd.DataFrame([{k: fx[k] for k in _feature_cols()}])
        pred = float(model.predict(X_row)[0])
        hist.loc[hist.index[-1], "load_kw"] = max(0.0, pred)
        generated_rows.append(
            {
                "datetime": next_dt,
                "department_id": str(dept_df["department_id"].iloc[0]),
                "prediction_load_kw": max(0.0, pred),
                "horizon_step": i + 1,
                "horizon_hours": horizon_hours,
            }
        )
    return pd.DataFrame(generated_rows)


def _detect_anomalies(
    dept_df: pd.DataFrame,
    model: XGBRegressor,
    lookback_rows: int,
    z_threshold: float,
) -> pd.DataFrame:
    work = _featureize(dept_df).dropna().reset_index(drop=True)
    if len(work) < max(100, lookback_rows):
        return pd.DataFrame(columns=["datetime", "department_id", "severity", "reason", "actual_kw", "expected_kw"])

    eval_df = work.tail(lookback_rows).copy()
    X = eval_df[_feature_cols()]
    expected = model.predict(X)
    actual = eval_df["load_kw"].astype(float).values
    resid = actual - expected
    med = float(np.median(resid))
    mad = float(np.median(np.abs(resid - med))) + 1e-9
    robust_z = 0.6745 * (resid - med) / mad

    alerts: list[dict[str, Any]] = []
    for i, z in enumerate(robust_z):
        absz = abs(float(z))
        if absz < z_threshold:
            continue
        sev = "critical" if absz >= z_threshold * 1.8 else "warning"
        direction = "spike_up" if resid[i] > 0 else "drop_down"
        alerts.append(
            {
                "datetime": pd.to_datetime(eval_df.iloc[i]["datetime"]),
                "department_id": str(eval_df.iloc[i]["department_id"]),
                "severity": sev,
                "reason": direction,
                "actual_kw": round(float(actual[i]), 3),
                "expected_kw": round(float(expected[i]), 3),
                "robust_z": round(float(z), 3),
            }
        )
    return pd.DataFrame(alerts)


def _ingest_updates(config: dict[str, Any], log_path: Path) -> pd.DataFrame:
    history_path = Path(config["paths"]["history_csv"])
    bootstrap_parquet_raw = (config.get("paths") or {}).get("bootstrap_parquet")
    bootstrap_parquet = Path(bootstrap_parquet_raw) if bootstrap_parquet_raw else None
    updates_dir = Path(config["paths"]["updates_dir"])
    archive_dir = Path(config["paths"]["archive_dir"])
    archive_dir.mkdir(parents=True, exist_ok=True)
    updates_dir.mkdir(parents=True, exist_ok=True)
    history = _load_history_csv(history_path, bootstrap_parquet=bootstrap_parquet)

    update_files = sorted(updates_dir.glob("*.csv"))
    if not update_files:
        _log(log_path, "[INGEST] No new files in updates_dir, using existing history only.")
        if history.empty:
            raise FileNotFoundError(f"No history and no updates found. updates_dir={updates_dir}")
        return history

    new_parts = []
    for path in update_files:
        normalized = _normalize_source(path, default_department=path.stem.replace("load_", "") or "default")
        new_parts.append(normalized)
        path.rename(archive_dir / path.name)
        _log(log_path, f"[INGEST] Archived processed file: {path.name}")

    new_df = pd.concat(new_parts, ignore_index=True)
    merged = pd.concat([history, new_df], ignore_index=True)
    merged["datetime"] = pd.to_datetime(merged["datetime"])
    merged["department_id"] = merged["department_id"].astype(str)
    merged["load_kw"] = pd.to_numeric(merged["load_kw"], errors="coerce").fillna(0.0)
    if "price_eur_kwh" not in merged.columns:
        merged["price_eur_kwh"] = np.nan
    merged = merged.sort_values(["department_id", "datetime"]).drop_duplicates(["department_id", "datetime"], keep="last")
    merged["price_eur_kwh"] = merged.groupby("department_id")["price_eur_kwh"].ffill().bfill()
    merged["price_eur_kwh"] = merged["price_eur_kwh"].fillna(0.1)

    history_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(history_path, index=False)
    _log(log_path, f"[INGEST] History updated: {history_path} ({len(merged)} rows)")
    return merged


def run_cycle(config_path: Path, horizon_hours: int) -> dict[str, Any]:
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    out_dir = Path(cfg["paths"]["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "sustainable_cycle.log"
    _log(log_path, "[START] sustainable cycle started")
    _log(log_path, f"[CONFIG] {config_path}")
    _log(log_path, f"[PARAM] horizon_hours={horizon_hours}")

    full = _ingest_updates(cfg, log_path)
    model_dir = Path(cfg["paths"]["model_registry_dir"])
    model_dir.mkdir(parents=True, exist_ok=True)
    train_cfg = cfg.get("training", {})
    anomaly_cfg = cfg.get("anomaly_detection", {})

    forecasts: list[pd.DataFrame] = []
    alerts: list[pd.DataFrame] = []
    train_results: list[dict[str, Any]] = []

    for dept, g in full.groupby("department_id"):
        dept_id = str(dept)
        dept_df = g.sort_values("datetime").reset_index(drop=True)
        step_minutes = _time_grid_mins(dept_df, default_minutes=int(train_cfg.get("default_step_minutes", 15)))
        tr = _train_or_incremental(dept_id, dept_df, model_dir, train_cfg, log_path)
        train_results.append(
            {
                "department_id": tr.department_id,
                "model_path": str(tr.model_path),
                "rows_used": tr.rows_used,
                "mode": tr.mode,
            }
        )
        model = joblib.load(tr.model_path)
        forecasts.append(_forecast_horizon(model, dept_df, horizon_hours=horizon_hours, step_minutes=step_minutes))
        alerts.append(
            _detect_anomalies(
                dept_df,
                model,
                lookback_rows=int(anomaly_cfg.get("lookback_rows", 672)),
                z_threshold=float(anomaly_cfg.get("z_threshold", 3.5)),
            )
        )

    forecast_df = pd.concat(forecasts, ignore_index=True).sort_values(["department_id", "datetime"])
    alerts_df = (
        pd.concat(alerts, ignore_index=True).sort_values(["severity", "datetime"], ascending=[False, True])
        if alerts
        else pd.DataFrame()
    )
    cycle_summary = {
        "horizon_hours": horizon_hours,
        "train_results": train_results,
        "forecast_rows": int(len(forecast_df)),
        "alert_rows": int(len(alerts_df)),
    }

    forecast_path = out_dir / "forecast_by_department.csv"
    alerts_path = out_dir / "anomaly_alerts.csv"
    summary_path = out_dir / "sustainable_cycle_summary.json"
    forecast_df.to_csv(forecast_path, index=False)
    if not alerts_df.empty:
        alerts_df.to_csv(alerts_path, index=False)
    else:
        pd.DataFrame(columns=["datetime", "department_id", "severity", "reason", "actual_kw", "expected_kw"]).to_csv(
            alerts_path, index=False
        )
    summary_path.write_text(json.dumps(cycle_summary, indent=2, ensure_ascii=False), encoding="utf-8")

    _log(log_path, f"[DONE] forecast={forecast_path}")
    _log(log_path, f"[DONE] alerts={alerts_path}")
    _log(log_path, f"[DONE] summary={summary_path}")
    return cycle_summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sustainable model cycle: ingest + incremental train + forecast + anomaly alerts"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("tests/sustainable/sustainable_cycle.yaml"),
        help="Path to sustainable cycle YAML config.",
    )
    parser.add_argument(
        "--horizon-hours",
        type=int,
        default=24,
        help="Forecast horizon in hours, selected by user.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    summary = run_cycle(args.config, horizon_hours=args.horizon_hours)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
