from __future__ import annotations

import hashlib
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
try:
    from domino.base_piece import BasePiece
except ModuleNotFoundError:
    from local_compat.base_piece import BasePiece

from .models import InputModel, OutputModel


def _to_numeric_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(",", ".", regex=False), errors="coerce")


def _pick_datetime_column(df: pd.DataFrame) -> str | None:
    aliases = {"datetime", "date time", "date_time", "timestamp", "time"}
    for c in df.columns:
        norm = str(c).replace("\ufeff", "").strip().lower()
        if norm in aliases:
            return c
    return None


def _read_csv_any(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=None, engine="python")
    if len(df.columns) == 1 and ";" in str(df.columns[0]):
        df = pd.read_csv(path, sep=";")
    return df


def _normalize(path: Path, default_department: str) -> pd.DataFrame:
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
            raise ValueError(f"{path.name}: no load columns found")
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


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _archive_target(archive_dir: Path, src_name: str) -> Path:
    candidate = archive_dir / src_name
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    idx = 1
    while True:
        alt = archive_dir / f"{stem}_{idx}{suffix}"
        if not alt.exists():
            return alt
        idx += 1


class SustainableIngestPiece(BasePiece):
    def piece_function(self, input_data: InputModel) -> OutputModel:
        log_path = Path(self.results_path) / "sustainable_ingest.log"
        err_path = Path(self.results_path) / "sustainable_ingest_error.txt"
        try:
            history_path = Path(input_data.history_csv)
            updates_dir = Path(input_data.updates_dir)
            archive_dir = Path(input_data.archive_dir)
            updates_dir.mkdir(parents=True, exist_ok=True)
            archive_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = Path(self.results_path) / "sustainable_ingest_manifest.json"

            if history_path.is_file():
                history = pd.read_csv(history_path, parse_dates=["datetime"])
            else:
                bootstrap = Path(input_data.bootstrap_parquet) if input_data.bootstrap_parquet else None
                if bootstrap and bootstrap.is_file():
                    history = pd.read_parquet(bootstrap)
                    if "department_id" not in history.columns:
                        history["department_id"] = "default"
                    if "price_eur_kwh" not in history.columns:
                        history["price_eur_kwh"] = 0.1
                    history = history[["datetime", "department_id", "load_kw", "price_eur_kwh"]].copy()
                else:
                    history = pd.DataFrame(columns=["datetime", "department_id", "load_kw", "price_eur_kwh"])

            files = sorted(updates_dir.glob("*.csv"))
            new_parts = []
            to_archive: list[tuple[Path, Path]] = []
            manifest: dict = {"processed": []}
            if manifest_path.is_file():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            processed = list(manifest.get("processed") or [])
            processed_hashes = {str(x.get("checksum")) for x in processed if x.get("checksum")}
            for path in files:
                checksum = _sha256(path)
                target = _archive_target(archive_dir, path.name)
                to_archive.append((path, target))
                if checksum in processed_hashes:
                    continue
                normalized = _normalize(path, default_department=path.stem.replace("load_", "") or "default")
                new_parts.append(normalized)
                processed.append(
                    {
                        "filename": path.name,
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

            history_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = history_path.with_suffix(history_path.suffix + ".tmp")
            merged.to_csv(tmp_path, index=False)
            tmp_path.replace(history_path)

            for src, dst in to_archive:
                src.rename(dst)

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
