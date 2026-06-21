from __future__ import annotations

import hashlib
import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
try:
    from domino.base_piece import BasePiece
except ModuleNotFoundError:
    from local_compat.base_piece import BasePiece

from .models import InputModel, OutputModel

# Shared OneData I/O layer (optional). Works in Domino (pieces dir on path) and
# local runs (repo root on path); degrades to local-only if unavailable.
try:
    from common import onedata_io as od
except ModuleNotFoundError:
    try:
        from pieces.common import onedata_io as od
    except ModuleNotFoundError:
        od = None


# --- I/O wrappers: route through the OneData layer when present (local paths
# are handled by pathlib/pandas unchanged), else plain local behaviour. ---
def _io_isfile(path: str) -> bool:
    return od.isfile(path) if od is not None else Path(path).is_file()


def _io_exists(path: str) -> bool:
    return od.exists(path) if od is not None else Path(path).exists()


def _io_makedirs(path: str) -> None:
    if od is not None:
        od.makedirs(path, exist_ok=True)
    else:
        Path(path).mkdir(parents=True, exist_ok=True)


def _io_ensure_parent(path: str) -> None:
    if od is not None:
        od.ensure_parent_dir(path)
    else:
        Path(path).parent.mkdir(parents=True, exist_ok=True)


def _io_glob(directory: str, pattern: str) -> list[str]:
    if od is not None:
        return od.glob(directory, pattern)
    return sorted(str(p) for p in Path(directory).glob(pattern))


def _io_read_csv(path: str, **kwargs) -> pd.DataFrame:
    return od.read_csv(path, **kwargs) if od is not None else pd.read_csv(path, **kwargs)


def _io_read_parquet(path: str) -> pd.DataFrame:
    return od.read_parquet(path) if od is not None else pd.read_parquet(path)


def _io_to_csv(df: pd.DataFrame, path: str, **kwargs) -> None:
    if od is not None:
        od.to_csv(df, path, **kwargs)
    else:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, **kwargs)


def _io_move(src: str, dst: str) -> None:
    if od is not None:
        od.move(src, dst)
    else:
        Path(src).rename(dst)


def _io_read_bytes(path: str) -> bytes:
    if od is not None and od.has_protocol(path):
        import fsspec

        with fsspec.open(str(path), "rb") as f:
            return f.read()
    with open(path, "rb") as f:
        return f.read()


def _is_remote(path: str) -> bool:
    return od is not None and od.has_protocol(path)


def _to_numeric_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(",", ".", regex=False), errors="coerce")


def _pick_datetime_column(df: pd.DataFrame) -> str | None:
    aliases = {"datetime", "date time", "date_time", "timestamp", "time"}
    for c in df.columns:
        norm = str(c).replace("\ufeff", "").strip().lower()
        if norm in aliases:
            return c
    return None


def _read_csv_any(path: str) -> pd.DataFrame:
    df = _io_read_csv(path, sep=None, engine="python")
    if len(df.columns) == 1 and ";" in str(df.columns[0]):
        df = _io_read_csv(path, sep=";")
    return df


def _normalize(path: str, default_department: str) -> pd.DataFrame:
    raw = _read_csv_any(path)
    dt_col = _pick_datetime_column(raw)
    if dt_col is None:
        raise ValueError(f"{os.path.basename(path)}: missing datetime column")
    df = raw.copy()
    dt_raw = df[dt_col].astype(str).str.strip()
    dt = pd.to_datetime(dt_raw, format="%d.%m.%y %H:%M", errors="coerce")
    if dt.isna().all():
        dt = pd.to_datetime(dt_raw, dayfirst=True, errors="coerce")
    df["datetime"] = dt
    df = df.dropna(subset=["datetime"])
    if "load_kw" in df.columns:
        out = pd.DataFrame(
            {
                "datetime": pd.to_datetime(df["datetime"]),
                "department_id": df.get("department_id", default_department).astype(str),
                "load_kw": _to_numeric_series(df["load_kw"]).fillna(0.0),
            }
        )
    else:
        cols = [c for c in df.columns if c not in {"datetime", "department_id", "price_eur_kwh", "price_eur_mwh"}]
        if not cols:
            raise ValueError(f"{os.path.basename(path)}: no load columns found")
        out = df.melt(id_vars=["datetime"], value_vars=cols, var_name="department_id", value_name="load_kw")
        out["department_id"] = out["department_id"].astype(str)
        out["load_kw"] = _to_numeric_series(out["load_kw"]).fillna(0.0)
    if "price_eur_kwh" in df.columns:
        out["price_eur_kwh"] = _to_numeric_series(df["price_eur_kwh"])
    elif "price_eur_mwh" in df.columns:
        out["price_eur_kwh"] = _to_numeric_series(df["price_eur_mwh"]) / 1000.0
    else:
        out["price_eur_kwh"] = pd.NA
    return out


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    if _is_remote(path):
        h.update(_io_read_bytes(path))
        return h.hexdigest()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _archive_target(archive_dir: str, src_name: str) -> str:
    candidate = f"{archive_dir.rstrip('/')}/{src_name}" if _is_remote(archive_dir) else str(Path(archive_dir) / src_name)
    if not _io_exists(candidate):
        return candidate
    stem, suffix = os.path.splitext(src_name)
    idx = 1
    while True:
        alt_name = f"{stem}_{idx}{suffix}"
        alt = f"{archive_dir.rstrip('/')}/{alt_name}" if _is_remote(archive_dir) else str(Path(archive_dir) / alt_name)
        if not _io_exists(alt):
            return alt
        idx += 1


def _write_history(merged: pd.DataFrame, history_path: str) -> None:
    """Persist the merged history. Local writes stay atomic (tmp + replace);
    remote writes go straight through the OneData backend."""
    if _is_remote(history_path):
        _io_ensure_parent(history_path)
        _io_to_csv(merged, history_path, index=False)
        return
    Path(history_path).parent.mkdir(parents=True, exist_ok=True)
    tmp_path = str(history_path) + ".tmp"
    merged.to_csv(tmp_path, index=False)
    os.replace(tmp_path, history_path)


class SustainableIngestPiece(BasePiece):
    def piece_function(self, input_data: InputModel, secrets_data=None) -> OutputModel:
        log_path = Path(self.results_path) / "sustainable_ingest.log"
        err_path = Path(self.results_path) / "sustainable_ingest_error.txt"
        try:
            # OneData is enabled only when secrets/env provide credentials.
            if od is not None and od.configure_onedata(secrets_data):
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write("[INFO] OneData backend configured\n")

            history_path = str(input_data.history_csv)
            updates_dir = str(input_data.updates_dir)
            archive_dir = str(input_data.archive_dir)
            _io_makedirs(updates_dir)
            _io_makedirs(archive_dir)
            # Manifest stays local to the piece run (Domino results dir).
            manifest_path = Path(self.results_path) / "sustainable_ingest_manifest.json"

            if _io_isfile(history_path):
                history = _io_read_csv(history_path, parse_dates=["datetime"])
            else:
                bootstrap = str(input_data.bootstrap_parquet) if input_data.bootstrap_parquet else None
                if bootstrap and _io_isfile(bootstrap):
                    history = _io_read_parquet(bootstrap)
                    if "department_id" not in history.columns:
                        history["department_id"] = "default"
                    if "price_eur_kwh" not in history.columns:
                        history["price_eur_kwh"] = 0.1
                    history = history[["datetime", "department_id", "load_kw", "price_eur_kwh"]].copy()
                else:
                    history = pd.DataFrame(columns=["datetime", "department_id", "load_kw", "price_eur_kwh"])

            files = _io_glob(updates_dir, "*.csv")
            new_parts = []
            to_archive: list[tuple[str, str]] = []
            manifest: dict = {"processed": []}
            if manifest_path.is_file():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            processed = list(manifest.get("processed") or [])
            processed_hashes = {str(x.get("checksum")) for x in processed if x.get("checksum")}
            for path in files:
                checksum = _sha256(path)
                name = os.path.basename(path)
                target = _archive_target(archive_dir, name)
                to_archive.append((path, target))
                if checksum in processed_hashes:
                    continue
                stem = os.path.splitext(name)[0]
                normalized = _normalize(path, default_department=stem.replace("load_", "") or "default")
                new_parts.append(normalized)
                processed.append(
                    {
                        "filename": name,
                        "checksum": checksum,
                        "rows": int(len(normalized)),
                        "ingested_at_utc": datetime.now(timezone.utc).isoformat(),
                    }
                )

            merged = pd.concat([history] + new_parts, ignore_index=True)
            merged["datetime"] = pd.to_datetime(merged["datetime"])
            merged["department_id"] = merged["department_id"].astype(str)
            merged["load_kw"] = pd.to_numeric(merged["load_kw"], errors="coerce").fillna(0.0)
            merged["price_eur_kwh"] = pd.to_numeric(merged["price_eur_kwh"], errors="coerce")
            merged = merged.sort_values(["department_id", "datetime"]).drop_duplicates(
                ["department_id", "datetime"], keep="last"
            )
            merged["price_eur_kwh"] = merged.groupby("department_id")["price_eur_kwh"].ffill().bfill().fillna(0.1)

            _write_history(merged, history_path)

            for src, dst in to_archive:
                _io_move(src, dst)

            manifest["processed"] = processed
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[INFO] rows_total={len(merged)}\n")
                f.write(f"[INFO] files_processed={len(files)}\n")
                f.write(f"[INFO] new_files_ingested={len(new_parts)}\n")

            return OutputModel(
                message=f"Ingest completed. rows={len(merged)}",
                history_csv_out=str(history_path),
                rows_total=int(len(merged)),
                departments=sorted(merged["department_id"].astype(str).unique().tolist()),
            )
        except Exception:
            err = traceback.format_exc()
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("[ERROR] SustainableIngestPiece failed\n")
                f.write(err + "\n")
            with open(err_path, "w", encoding="utf-8") as f:
                f.write(err)
            raise
