"""
Generate tests/PredictPiece_Inputs/predict_planned_load_halfyear.csv
- bridge (4x real load_kw) + future horizon for each department.

Run from Alternate project root:
  python scripts/generate_predict_planned_csv.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOAD_DIR = PROJECT_ROOT / "tests" / "FetchEnergyDataPiece_Inputs"
OUT_CSV = PROJECT_ROOT / "tests" / "PredictPiece_Inputs" / "predict_planned_load_halfyear.csv"
FUTURE_START = pd.Timestamp("2025-07-01 00:00:00")
DAYS_FUTURE = 7


def _to_numeric_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(",", ".", regex=False), errors="coerce")


def _pick_datetime_column(df: pd.DataFrame) -> str | None:
    aliases = {"datetime", "date time", "date_time", "timestamp", "time"}
    for c in df.columns:
        if str(c).replace("\ufeff", "").strip().lower() in aliases:
            return c
    return None


def _read_load_csv(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path, sep=None, engine="python")
    if len(raw.columns) == 1 and ";" in str(raw.columns[0]):
        raw = pd.read_csv(path, sep=";")

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
        df["load_kw"] = _to_numeric_series(df["load_kw"]).fillna(0.0)
        if "department_id" not in df.columns:
            dept = path.stem.replace("load_", "")
            df["department_id"] = "default" if dept == "load" else dept
        return df[["datetime", "department_id", "load_kw"]]

    reserved = {"department_id", "price_eur_kwh", "price_eur_mwh"}
    value_cols = [c for c in df.columns if c not in reserved]
    if not value_cols:
        raise ValueError(f"{path.name}: no load columns found")
    long = df.melt(
        id_vars=["datetime"],
        value_vars=value_cols,
        var_name="department_id",
        value_name="load_kw",
    )
    long["department_id"] = long["department_id"].astype(str).str.strip().str.replace("prikon ", "", case=False)
    long["load_kw"] = _to_numeric_series(long["load_kw"]).fillna(0.0)
    return long[["datetime", "department_id", "load_kw"]]


def main() -> None:
    load_files = sorted(LOAD_DIR.glob("load*.csv"))
    if not load_files:
        load_files = [p for p in sorted(LOAD_DIR.glob("*.csv")) if "price" not in p.name.lower()]
    if not load_files:
        raise FileNotFoundError(f"Missing input load CSV files in {LOAD_DIR}")

    n_future = DAYS_FUTURE * 96
    future_dt = pd.date_range(FUTURE_START, periods=n_future, freq="15min")
    h = future_dt.hour.values
    price = 0.07 + 0.035 * (h >= 7) * (h <= 20)
    price = np.clip(price, 0.06, 0.15)
    future_base = pd.DataFrame({"datetime": future_dt, "load_kw": 0.0, "price_eur_kwh": price})

    all_load_parts = []
    for lf in load_files:
        all_load_parts.append(_read_load_csv(lf))
    load_all = pd.concat(all_load_parts, ignore_index=True).sort_values(["department_id", "datetime"]).reset_index(drop=True)

    parts = []
    for dept, g in load_all.groupby("department_id"):
        dept_id = str(dept)
        g = g.sort_values("datetime").reset_index(drop=True)
        if len(g) < 4:
            continue
        bridge = g.tail(4)[["datetime", "load_kw"]].copy()
        bridge["datetime"] = pd.date_range(
            end=FUTURE_START - pd.Timedelta(minutes=15),
            periods=4,
            freq="15min",
        )
        bridge["price_eur_kwh"] = 0.085
        bridge["department_id"] = dept_id

        future = future_base.copy()
        future["department_id"] = dept_id
        parts.append(pd.concat([bridge, future], ignore_index=True))

    if not parts:
        raise RuntimeError("No valid department data found for planned prediction generation.")

    out = pd.concat(parts, ignore_index=True).sort_values(["department_id", "datetime"]).reset_index(drop=True)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)
    print(f"OK: {OUT_CSV} ({len(out)} rows)")


if __name__ == "__main__":
    main()
