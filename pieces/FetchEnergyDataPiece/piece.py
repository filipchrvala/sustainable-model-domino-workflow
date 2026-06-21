try:
    from domino.base_piece import BasePiece
except ModuleNotFoundError:
    from local_compat.base_piece import BasePiece
from .models import InputModel, OutputModel
import os
import pandas as pd
from pathlib import Path
import traceback

# Shared OneData I/O layer. Import works both in Domino (pieces dir on path)
# and in local runs (repo root on path). Falls back to local-only stubs if the
# module is somehow unavailable, so the piece never fails to import.
try:
    from common import onedata_io as od
except ModuleNotFoundError:
    try:
        from pieces.common import onedata_io as od
    except ModuleNotFoundError:
        od = None


def _stem(path: str) -> str:
    return os.path.splitext(os.path.basename(str(path)))[0]


# Thin I/O wrappers: use the shared OneData layer when present (it routes local
# paths to pathlib/pandas unchanged), else fall back to plain local behaviour.
def _io_isfile(path: str) -> bool:
    return od.isfile(path) if od is not None else Path(path).is_file()


def _io_isdir(path: str) -> bool:
    return od.isdir(path) if od is not None else Path(path).is_dir()


def _io_glob(directory: str, pattern: str) -> list[str]:
    if od is not None:
        return od.glob(directory, pattern)
    return sorted(str(p) for p in Path(directory).glob(pattern))


def _io_read_csv(path: str, **kwargs) -> pd.DataFrame:
    return od.read_csv(path, **kwargs) if od is not None else pd.read_csv(path, **kwargs)


def _to_numeric_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(",", ".", regex=False), errors="coerce")


def _pick_datetime_column(df: pd.DataFrame) -> str | None:
    aliases = {"datetime", "date time", "date_time", "timestamp", "time"}
    for c in df.columns:
        norm = str(c).replace("\ufeff", "").strip().lower()
        if norm in aliases:
            return c
    return None


def _normalize_load_frame(raw: pd.DataFrame, source_name: str) -> pd.DataFrame:
    dt_col = _pick_datetime_column(raw)
    if dt_col is None:
        raise ValueError(f"{source_name}: missing datetime column")

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
            dept = source_name.replace("load_", "") or "default"
            df["department_id"] = dept if dept != "load" else "default"
        return df[["datetime", "department_id", "load_kw"]]

    reserved = {"department_id", "price_eur_kwh", "price_eur_mwh"}
    value_cols = [c for c in df.columns if c not in reserved]
    if not value_cols:
        raise ValueError(f"{source_name}: no load columns found")

    long = df.melt(
        id_vars=["datetime"],
        value_vars=value_cols,
        var_name="department_id",
        value_name="load_kw",
    )
    long["department_id"] = long["department_id"].astype(str).str.strip().str.replace("prikon ", "", case=False)
    long["load_kw"] = _to_numeric_series(long["load_kw"]).fillna(0.0)
    return long[["datetime", "department_id", "load_kw"]]


def _log(results_path: str | None, message: str) -> None:
    print(message)
    if not results_path:
        return
    p = Path(results_path)
    p.mkdir(parents=True, exist_ok=True)
    with open(p / "fetch_energy_data.log", "a", encoding="utf-8") as f:
        f.write(message + "\n")


class FetchEnergyDataPiece(BasePiece):
    """
    Load and merge energy CSV files from shared storage
    """

    def piece_function(self, input_data: InputModel, secrets_data=None) -> OutputModel:
        try:
            _log(self.results_path, "[INFO] FetchEnergyDataPiece started")
            _log(self.results_path, f"[INFO] Load CSV: {input_data.load_csv}")
            _log(self.results_path, f"[INFO] Prices CSV: {input_data.prices_csv}")

            # Configure OneData only when secrets are supplied (Domino) or env
            # vars are set; otherwise everything stays on the local filesystem.
            if od is not None and od.configure_onedata(secrets_data):
                _log(self.results_path, "[INFO] OneData backend configured for inputs")

            load_csv = str(input_data.load_csv)
            prices_csv = str(input_data.prices_csv)

            prices_df = pd.DataFrame()
            if prices_csv and _io_isfile(prices_csv):
                prices_df = _io_read_csv(prices_csv, parse_dates=["datetime"])
                prices_df = prices_df.set_index("datetime")
            else:
                _log(self.results_path, "[WARN] Prices CSV not found; continuing without price columns")

            if _io_isdir(load_csv):
                load_files = _io_glob(load_csv, "load*.csv")
                if not load_files:
                    load_files = [p for p in _io_glob(load_csv, "*.csv") if "price" not in os.path.basename(p).lower()]
            elif _io_isfile(load_csv):
                load_files = [load_csv]
            else:
                load_files = []
            if not load_files:
                message = f"No load CSV files found at: {load_csv}"
                _log(self.results_path, f"[ERROR] {message}")
                return OutputModel(message=message, output_path="")

            _log(self.results_path, "[INFO] Reading CSV files")
            merged_parts = []
            for lf in load_files:
                raw = _io_read_csv(lf, sep=None, engine="python")
                if len(raw.columns) == 1 and ";" in str(raw.columns[0]):
                    raw = _io_read_csv(lf, sep=";")
                load_df = _normalize_load_frame(raw, _stem(lf)).set_index("datetime")
                if not prices_df.empty:
                    part = load_df.join(prices_df, how="left").reset_index()
                else:
                    part = load_df.reset_index()
                merged_parts.append(part)

            _log(self.results_path, "[INFO] Merging data")
            merged_df = pd.concat(merged_parts, ignore_index=True)
            merged_df = merged_df.sort_values(["department_id", "datetime"]).reset_index(drop=True)

            if "price_eur_mwh" in merged_df.columns:
                merged_df["price_eur_mwh"] = merged_df.groupby("department_id")["price_eur_mwh"].ffill().bfill()
            if "price_eur_kwh" in merged_df.columns:
                merged_df["price_eur_kwh"] = merged_df.groupby("department_id")["price_eur_kwh"].ffill().bfill()

            output_path = Path(self.results_path) / "merged_energy_data.parquet"
            merged_df.to_parquet(output_path, index=False)

            _log(self.results_path, f"[SUCCESS] Data merged, rows: {len(merged_df)}")
            _log(self.results_path, f"[SUCCESS] Output written to {output_path}")

            self.display_result = {"file_type": "parquet", "file_path": str(output_path)}
            return OutputModel(
                message=f"Data merged successfully ({len(merged_df)} rows)",
                output_path=str(output_path),
            )
        except Exception:
            err = traceback.format_exc()
            _log(self.results_path, f"[ERROR] {err}")
            if self.results_path:
                with open(Path(self.results_path) / "fetch_energy_data_error.txt", "w", encoding="utf-8") as f:
                    f.write(err)
            raise
