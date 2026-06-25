"""Build ~1-week Domino/OneData test inputs from full seed files.

Writes under tests/weekly/ and copies workflow-facing names used by upload_onedata_inputs.py.
Run:  python scripts/generate_weekly_test_data.py
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import yaml

REPO = Path(__file__).resolve().parent.parent
WEEKLY = REPO / "tests" / "weekly"
DAYS = 7


def _slice_csv(src: Path, out: Path, *, days: int = DAYS) -> int:
    df = pd.read_csv(src, sep=None, engine="python", encoding="utf-8-sig")
    cols = {c: c.strip().lower().replace(" ", "_") for c in df.columns}
    df = df.rename(columns=cols)
    if "datetime" not in df.columns:
        raise ValueError(f"{src}: missing datetime column")
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    df = df.dropna(subset=["datetime"]).sort_values("datetime")
    t0 = df["datetime"].min()
    t1 = t0 + pd.Timedelta(days=days)
    slim = df[(df["datetime"] >= t0) & (df["datetime"] < t1)].copy()
    out.parent.mkdir(parents=True, exist_ok=True)
    slim.to_csv(out, index=False)
    return len(slim)


def _weekly_scenario(src: Path, out: Path) -> None:
    cfg = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
    equip = cfg.setdefault("equipment", {})
    equip["selection_mode"] = "manual"
    auto = equip.get("auto") or {}
    auto["max_configurations"] = 12
    equip["auto"] = auto
    out.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")


def main() -> None:
    WEEKLY.mkdir(parents=True, exist_ok=True)

    load_src = REPO / "tests" / "FetchEnergyDataPiece_Inputs" / "load_seed.csv"
    predict_src = REPO / "tests" / "PredictPiece_Inputs" / "predict_planned_load_halfyear.csv"
    history_src = REPO / "tests" / "sustainable" / "history" / "energy_history.csv"
    scenario_src = REPO / "tests" / "user_input" / "scenario.yaml"
    wf_src = REPO / "tests" / "user_input" / "workflow_user_input.json"

    n_load = _slice_csv(load_src, WEEKLY / "load.csv")
    n_pred = _slice_csv(predict_src, WEEKLY / "predict_planned_load_halfyear.csv")
    n_hist = _slice_csv(history_src, WEEKLY / "sustainable" / "history" / "energy_history.csv")
    _weekly_scenario(scenario_src, WEEKLY / "scenario.yaml")

    if wf_src.is_file():
        shutil.copy2(wf_src, WEEKLY / "workflow_user_input.json")
    else:
        (WEEKLY / "workflow_user_input.json").write_text("{}", encoding="utf-8")

    # prices from weekly load timestamps
    load = pd.read_csv(WEEKLY / "load.csv")
    prices = load[["datetime"]].drop_duplicates().copy()
    prices["price_eur_per_kwh"] = 0.10
    prices.to_csv(WEEKLY / "prices.csv", index=False)

    meta = {
        "days": DAYS,
        "rows": {"load.csv": n_load, "predict_planned_load_halfyear.csv": n_pred, "energy_history.csv": n_hist},
        "selection_mode": "manual",
        "note": "Upload with: python scripts/upload_onedata_inputs.py --weekly",
    }
    (WEEKLY / "README.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Wrote tests/weekly/  load={n_load} predict={n_pred} history={n_hist} rows (~{DAYS} days each)")


if __name__ == "__main__":
    main()
