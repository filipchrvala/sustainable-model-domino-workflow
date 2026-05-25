from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import yaml
try:
    from domino.base_piece import BasePiece
except ModuleNotFoundError:
    from local_compat.base_piece import BasePiece

from .models import InputModel, OutputModel


def _discover_workflow_user_input_path(load_csv: Path, scenario_yaml: Path) -> Path | None:
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        scenario_yaml.with_name("workflow_user_input.json"),
        load_csv.with_name("workflow_user_input.json"),
        load_csv.parent / "workflow_user_input.json",
        repo_root / "tests" / "user_input" / "workflow_user_input.json",
    ]
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_file():
            return candidate
    return None


class UserInputPiece(BasePiece):
    """Validate and pass-through user inputs for downstream pieces."""

    @staticmethod
    def _read_csv_auto(path: Path) -> pd.DataFrame:
        return pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig", decimal=",")

    @staticmethod
    def _normalize_datetime_column(df: pd.DataFrame) -> pd.DataFrame:
        cols = {c: c.strip().lower().replace(" ", "_") for c in df.columns}
        df = df.rename(columns=cols)
        dt_col = None
        for cand in ("datetime", "date_time", "timestamp"):
            if cand in df.columns:
                dt_col = cand
                break
        if dt_col is None:
            raise ValueError("CSV must contain datetime/date_time/timestamp column")
        raw_dt = df[dt_col].astype(str).str.strip()
        # Support both ISO (YYYY-MM-DD ...) and local day-first formats (dd.mm.yyyy ...).
        dt_iso = pd.to_datetime(raw_dt, errors="coerce", dayfirst=False, format="mixed")
        dt_local = pd.to_datetime(raw_dt, errors="coerce", dayfirst=True, format="mixed")
        df["datetime"] = dt_iso.fillna(dt_local)
        return df.dropna(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)

    @staticmethod
    def _collapse_duplicate_timestamps(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or "datetime" not in df.columns:
            return df
        if not df["datetime"].duplicated().any():
            return df

        agg: dict[str, str] = {}
        for col in df.columns:
            if col == "datetime":
                continue
            if col == "load_kw":
                agg[col] = "sum"
            elif col == "price_eur_per_kwh":
                agg[col] = "mean"
            else:
                agg[col] = "first"
        return df.groupby("datetime", as_index=False).agg(agg).sort_values("datetime").reset_index(drop=True)

    @staticmethod
    def _infer_step_hours(df: pd.DataFrame, fallback_minutes: float = 15.0) -> float:
        if len(df) < 2:
            return max(fallback_minutes, 1.0) / 60.0
        step = df["datetime"].diff().dt.total_seconds().median()
        if pd.notna(step) and step > 0:
            return float(step) / 3600.0
        return max(fallback_minutes, 1.0) / 60.0

    @staticmethod
    def _repair_missing_intervals(df: pd.DataFrame, step_hours: float) -> tuple[pd.DataFrame, int]:
        if df.empty:
            return df, 0
        step_minutes = max(1, int(round(step_hours * 60.0)))
        freq = f"{step_minutes}min"
        full_index = pd.date_range(df["datetime"].min(), df["datetime"].max(), freq=freq)
        repaired = (
            df.set_index("datetime")
            .reindex(full_index)
            .rename_axis("datetime")
            .reset_index()
            .sort_values("datetime")
            .reset_index(drop=True)
        )
        filled = int(repaired["load_kw"].isna().sum()) if "load_kw" in repaired.columns else 0
        if "load_kw" in repaired.columns:
            repaired["load_kw"] = pd.to_numeric(repaired["load_kw"], errors="coerce").interpolate(
                method="linear", limit_direction="both"
            ).fillna(0.0)
        if "price_eur_per_kwh" in repaired.columns:
            repaired["price_eur_per_kwh"] = pd.to_numeric(repaired["price_eur_per_kwh"], errors="coerce")
            med = float(repaired["price_eur_per_kwh"].median()) if repaired["price_eur_per_kwh"].notna().any() else 0.0
            repaired["price_eur_per_kwh"] = repaired["price_eur_per_kwh"].interpolate(
                method="linear", limit_direction="both"
            ).fillna(med)
        return repaired, filled

    def piece_function(self, input_data: InputModel) -> OutputModel:
        load_csv = Path(input_data.load_csv)
        prices_csv = Path(input_data.prices_csv) if input_data.prices_csv else None
        scenario_yaml = Path(input_data.scenario_yaml)
        out_dir = Path(self.results_path or load_csv.parent)
        out_dir.mkdir(parents=True, exist_ok=True)
        log_path = out_dir / "user_input.log"

        def _log(msg: str) -> None:
            text = f"[UserInputPiece] {msg}"
            print(text, flush=True)
            with log_path.open("a", encoding="utf-8") as f:
                f.write(text + "\n")

        _log(f"Input load_csv={load_csv}")
        _log(f"Input prices_csv={prices_csv}")
        _log(f"Input scenario_yaml={scenario_yaml}")
        if not load_csv.is_file():
            raise FileNotFoundError(f"Load CSV not found: {load_csv}")
        if not scenario_yaml.is_file():
            raise FileNotFoundError(f"Scenario YAML not found: {scenario_yaml}")
        scenario_copy = out_dir / "scenario_resolved.yaml"
        shutil.copy2(scenario_yaml, scenario_copy)
        _log(f"Copied scenario to shared output path: {scenario_copy}")
        scenario = yaml.safe_load(scenario_copy.read_text(encoding="utf-8")) or {}
        timestep_minutes = float(scenario.get("timestep_minutes", 15))
        prod_cfg = scenario.get("production") or {}
        gap_repair_enabled = bool(prod_cfg.get("gap_repair_enabled", True))

        # Case A: load_csv already contains both load_kw and price_eur_per_kwh.
        df = self._normalize_datetime_column(self._read_csv_auto(load_csv))
        cols = [c.strip().lower().replace(" ", "_") for c in df.columns]
        df.columns = cols
        has_load_kw = "load_kw" in df.columns
        has_price = "price_eur_per_kwh" in df.columns
        merge_mode = "single_csv"
        overlap_rows = None
        if has_load_kw and has_price:
            merged = df.copy()
            merged["load_kw"] = pd.to_numeric(merged["load_kw"], errors="coerce").fillna(0.0)
            merged["price_eur_per_kwh"] = pd.to_numeric(merged["price_eur_per_kwh"], errors="coerce")
            merged = self._collapse_duplicate_timestamps(
                merged[["datetime", "load_kw", "price_eur_per_kwh"]].dropna(subset=["price_eur_per_kwh"])
            )
            merged_path = out_dir / "load_and_prices_merged.csv"
            merged.to_csv(merged_path, index=False)
            merge_mode = "single_csv_normalized"
        else:
            # Case B: two CSV inputs (consumption + prices) -> merge to one normalized file.
            if prices_csv is None or not prices_csv.is_file():
                raise ValueError(
                    "Provide either single CSV with load_kw + price_eur_per_kwh, or two CSV files (load_csv + prices_csv)."
                )

            # Build load series
            load_df = df.copy()
            if "load_kw" not in load_df.columns:
                load_candidates = [c for c in load_df.columns if c not in {"datetime"}]
                if not load_candidates:
                    raise ValueError("Load CSV must contain load_kw or numeric consumption columns.")
                load_df["load_kw"] = (
                    load_df[load_candidates].apply(pd.to_numeric, errors="coerce").fillna(0.0).sum(axis=1)
                )
            load_df = load_df[["datetime", "load_kw"]]
            load_df = self._collapse_duplicate_timestamps(load_df)

            # Build price series
            p = self._normalize_datetime_column(self._read_csv_auto(prices_csv))
            p.columns = [c.strip().lower().replace(" ", "_") for c in p.columns]
            if "price_eur_per_kwh" not in p.columns:
                if "price_eur_kwh" in p.columns:
                    p = p.rename(columns={"price_eur_kwh": "price_eur_per_kwh"})
                else:
                    raise ValueError("Prices CSV must contain price_eur_per_kwh (or price_eur_kwh).")
            p = p[["datetime", "price_eur_per_kwh"]]
            p = self._collapse_duplicate_timestamps(p)

            merged = load_df.merge(p, on="datetime", how="inner").dropna(subset=["price_eur_per_kwh"])
            if merged.empty:
                raise ValueError("No overlapping datetimes between load CSV and prices CSV.")
            merge_mode = "two_csv_merged"
            overlap_rows = int(len(merged))
            merged_path = out_dir / "load_and_prices_merged.csv"
            merged.to_csv(merged_path, index=False)

        merged_df = self._read_csv_auto(Path(merged_path))
        merged_df = self._normalize_datetime_column(merged_df)
        inferred_step_h = self._infer_step_hours(merged_df, fallback_minutes=timestep_minutes)
        configured_step_h = max(timestep_minutes, 1.0) / 60.0
        repair_step_h = min(inferred_step_h, configured_step_h)
        repaired_intervals = 0
        if gap_repair_enabled:
            merged_df, repaired_intervals = self._repair_missing_intervals(merged_df, repair_step_h)
            merged_df.to_csv(merged_path, index=False)
        start_dt = merged_df["datetime"].min()
        end_dt = merged_df["datetime"].max()
        expected_intervals = int(round(((end_dt - start_dt).total_seconds() / 3600.0) / repair_step_h)) + 1
        missing_intervals_est = max(0, expected_intervals - len(merged_df))
        summary = {
            "message": "User input validated",
            "merge_mode": merge_mode,
            "input_paths": {
                "load_csv": str(load_csv),
                "prices_csv": str(prices_csv) if prices_csv else "",
                "scenario_yaml": str(scenario_yaml),
            },
            "resolved_paths": {
                "load_csv": str(merged_path),
                "scenario_yaml": str(scenario_copy),
            },
            "rows_merged": int(len(merged_df)),
            "rows_overlap_when_two_csv": overlap_rows,
            "datetime_min": str(merged_df["datetime"].min()),
            "datetime_max": str(merged_df["datetime"].max()),
            "inferred_step_hours": round(inferred_step_h, 6),
            "repair_step_hours": round(repair_step_h, 6),
            "expected_intervals_in_range": expected_intervals,
            "missing_intervals_estimate": int(missing_intervals_est),
            "gap_repair_enabled": gap_repair_enabled,
            "repaired_intervals_count": int(repaired_intervals),
        }
        (out_dir / "user_input_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (out_dir / "user_input_validated.json").write_text(
            json.dumps(summary["resolved_paths"], indent=2, ensure_ascii=False), encoding="utf-8"
        )
        workflow_input_copy = out_dir / "workflow_user_input.json"
        workflow_input_source = _discover_workflow_user_input_path(load_csv, scenario_yaml)
        if workflow_input_source is not None:
            shutil.copy2(workflow_input_source, workflow_input_copy)
            _log(f"Copied workflow_user_input_json from {workflow_input_source}")
        else:
            workflow_input_copy.write_text("{}", encoding="utf-8")
            _log("workflow_user_input.json not found near inputs; wrote empty fallback")

        return OutputModel(
            message="User input validated",
            load_csv=str(merged_path),
            scenario_yaml=str(scenario_copy),
            workflow_user_input_json=str(workflow_input_copy),
        )
