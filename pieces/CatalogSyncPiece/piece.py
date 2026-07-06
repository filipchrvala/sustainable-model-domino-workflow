from __future__ import annotations

import json
import re
import traceback
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

import pandas as pd
import yaml
try:
    from domino.base_piece import BasePiece
except ModuleNotFoundError:
    from local_compat.base_piece import BasePiece

from .models import InputModel, OutputModel

DEFAULT_PV_URL = "https://raw.githubusercontent.com/NREL/SAM/patch/deploy/libraries/CEC%20Modules.csv"
DEFAULT_INV_URL = "https://raw.githubusercontent.com/NREL/SAM/develop/deploy/libraries/CEC%20Inverters.csv"


class CatalogSyncPiece(BasePiece):
    """Download and normalize online hardware catalogs."""

    @staticmethod
    def _project_root() -> Path:
        return Path(__file__).resolve().parents[2]

    def piece_function(self, input_data: InputModel) -> OutputModel:
        scenario_path = Path(input_data.scenario_yaml)
        out_dir = Path(self.results_path or scenario_path.parent)
        out_dir.mkdir(parents=True, exist_ok=True)
        log_path = out_dir / "catalog_sync.log"

        def _log(msg: str) -> None:
            text = f"[CatalogSyncPiece] {msg}"
            print(text, flush=True)
            with log_path.open("a", encoding="utf-8") as f:
                f.write(text + "\n")

        _log(f"Input scenario_yaml={scenario_path}")
        if not scenario_path.is_file():
            raise FileNotFoundError(f"Scenario YAML not found: {scenario_path}")
        try:
            cfg = yaml.safe_load(scenario_path.read_text(encoding="utf-8")) or {}
            src = (cfg.get("catalog") or {}).get("sources") or {}
            pv_url = str(src.get("pv_modules_url") or DEFAULT_PV_URL)
            inv_url = str(src.get("inverters_url") or DEFAULT_INV_URL)
            bat_url = str(src.get("battery_products_url") or "").strip()
            _log(f"Catalog URLs set: pv={pv_url}, inv={inv_url}, bat={bat_url or 'N/A'}")

            url_outage = False
            warnings: list[str] = []
            source_mode = {"pv_modules": "online", "inverters": "online", "battery_products": "local_default"}

            pv_df: pd.DataFrame | None = None
            try:
                pv_df = pd.read_csv(pv_url, low_memory=False)
            except Exception as exc:
                url_outage = True
                source_mode["pv_modules"] = "fallback_local"
                warnings.append(f"PV catalog URL unavailable: {pv_url} ({exc})")
                local_pv = self._project_root() / "catalog" / "pv_modules_catalog.json"
                if local_pv.is_file():
                    loc = json.loads(local_pv.read_text(encoding="utf-8"))
                    pv_df = pd.DataFrame(loc.get("modules") or [])
                else:
                    raise RuntimeError(f"PV URL failed and no local fallback found: {local_pv}") from exc

            inv_df: pd.DataFrame | None = None
            try:
                inv_df = pd.read_csv(inv_url, low_memory=False)
            except Exception as exc:
                url_outage = True
                source_mode["inverters"] = "fallback_cache_or_empty"
                warnings.append(f"Inverter catalog URL unavailable: {inv_url} ({exc})")
                cache_inv = out_dir / "inverters_online.json"
                if cache_inv.is_file():
                    cached = json.loads(cache_inv.read_text(encoding="utf-8"))
                    inv_df = pd.DataFrame(cached.get("items") or [])
                else:
                    inv_df = pd.DataFrame([])

            bat_products: list[dict] = []
            local_bt = self._project_root() / "catalog" / "battery_catalog.json"
            if bat_url:
                try:
                    if bat_url.lower().endswith(".json"):
                        with urlopen(bat_url, timeout=30) as resp:
                            payload = json.loads(resp.read().decode("utf-8"))
                        if isinstance(payload, dict):
                            bat_products = list(payload.get("products") or payload.get("items") or [])
                    else:
                        try:
                            with urlopen(bat_url, timeout=30) as resp:
                                raw = resp.read()
                            bdf_raw = pd.read_excel(BytesIO(raw), header=None)
                            header_idx = None
                            for i in range(min(len(bdf_raw), 40)):
                                row_vals = [str(v).strip() for v in bdf_raw.iloc[i].tolist()]
                                has_man = any(v.lower() == "manufacturer name" for v in row_vals)
                                has_model = any(v.lower() == "model number" for v in row_vals)
                                if has_man and has_model:
                                    header_idx = i
                                    break
                            if header_idx is not None:
                                cols_raw = [str(v).strip() for v in bdf_raw.iloc[header_idx].tolist()]
                                cols = [c if c and c.lower() != "nan" else f"col_{j}" for j, c in enumerate(cols_raw)]
                                bdf = bdf_raw.iloc[header_idx + 2 :].copy()
                                bdf.columns = cols
                                bdf = bdf.reset_index(drop=True)
                            else:
                                bdf = pd.read_excel(BytesIO(raw))
                        except Exception:
                            bdf = pd.read_csv(bat_url, low_memory=False)
                        cols = {str(c).strip().lower().replace(" ", "_"): c for c in bdf.columns}
                        man_col = cols.get("manufacturer") or cols.get("manufacturer_name")
                        model_col = cols.get("model_name") or cols.get("model") or cols.get("model_number")
                        desc_col = cols.get("description")
                        energy_col = (
                            cols.get("nameplate_energy_capacity")
                            or cols.get("nominal_kwh")
                            or cols.get("energy_kwh")
                        )
                        if energy_col is None:
                            for c in bdf.columns:
                                c_key = str(c).strip().lower()
                                if "nameplate" in c_key and "energy" in c_key:
                                    energy_col = c
                                    break
                        power_col = (
                            cols.get("max_continuous_discharge_rate(kW)".lower().replace(" ", "_"))
                            or cols.get("max_continuous_discharge_rate")
                            or cols.get("max_power_kw")
                            or cols.get("power_kw")
                        )
                        if power_col is None:
                            for c in bdf.columns:
                                c_key = str(c).strip().lower()
                                if "max" in c_key and "discharge" in c_key and "rate" in c_key:
                                    power_col = c
                                    break
                        for _, r in bdf.iterrows():
                            if man_col is None and "col_0" in bdf.columns:
                                man_col = "col_0"
                            if model_col is None and "col_2" in bdf.columns:
                                model_col = "col_2"
                            if desc_col is None and "col_4" in bdf.columns:
                                desc_col = "col_4"

                            nominal = pd.to_numeric(
                                pd.Series([r.get(energy_col, r.get("nominal_kwh", r.get("energy_kwh", 0)))]), errors="coerce"
                            ).fillna(0.0).iloc[0]
                            pmax = pd.to_numeric(
                                pd.Series([r.get(power_col, r.get("max_power_kw", r.get("power_kw", 0)))]), errors="coerce"
                            ).fillna(0.0).iloc[0]
                            desc_txt = str(r.get(desc_col, "")) if desc_col else ""
                            if nominal <= 0 and desc_txt:
                                m_kwh = re.search(r"([0-9]+(?:\\.[0-9]+)?)\\s*kwh", desc_txt, flags=re.IGNORECASE)
                                if m_kwh:
                                    nominal = float(m_kwh.group(1))
                            if pmax <= 0 and desc_txt:
                                m_kw = re.search(r"([0-9]+(?:\\.[0-9]+)?)\\s*kw", desc_txt, flags=re.IGNORECASE)
                                if m_kw:
                                    pmax = float(m_kw.group(1))
                            if nominal <= 0:
                                continue
                            manufacturer = str(r.get(man_col, r.get("manufacturer", ""))).strip()
                            model = str(r.get(model_col, r.get("model", ""))).strip()
                            raw_id = f"{manufacturer}_{model}_{int(round(float(nominal)))}"
                            norm_id = re.sub(r"[^a-zA-Z0-9_]+", "_", raw_id).strip("_").lower()
                            bat_products.append(
                                {
                                    "id": str(r.get("id", norm_id or f"bat_{int(nominal)}")).strip(),
                                    "manufacturer": manufacturer,
                                    "product_line": str(r.get("product_line", model)).strip(),
                                    "nominal_kwh": float(nominal),
                                    "max_power_kw": float(pmax),
                                    "chemistry": str(r.get("chemistry", "LFP")).strip() or "LFP",
                                    "form_factor": str(r.get("form_factor", "container")).strip() or "container",
                                }
                            )
                    if bat_products:
                        source_mode["battery_products"] = "online"
                    else:
                        source_mode["battery_products"] = "fallback_local"
                        warnings.append(
                            f"Battery catalog URL parsed but no valid rows found: {bat_url}. Using local fallback."
                        )
                except Exception as exc:
                    url_outage = True
                    source_mode["battery_products"] = "fallback_local"
                    warnings.append(f"Battery catalog URL unavailable: {bat_url} ({exc})")
            if not bat_products and local_bt.is_file():
                loc_bt = json.loads(local_bt.read_text(encoding="utf-8"))
                bat_products = list(loc_bt.get("products") or [])
            pv = []
            for _, r in pv_df.iterrows():
                name = str(r.get("Name", "")).strip()
                if not name:
                    continue
                stc = pd.to_numeric(
                    pd.Series([r.get("STC", r.get("power_wp", 0))]),
                    errors="coerce",
                ).fillna(0.0).iloc[0]
                pv.append(
                    {
                        "name": name,
                        "manufacturer": (
                            name.split(":")[0].strip() if ":" in name else str(r.get("manufacturer", ""))
                        ),
                        "model": name.split(":", 1)[1].strip() if ":" in name else str(r.get("model", name)),
                        "technology": r.get("Technology", r.get("technology")),
                        "bifacial": str(r.get("Bifacial", r.get("bifacial", ""))).upper() in ("Y", "TRUE", "1"),
                        "stc_watts": float(stc),
                    }
                )
            inv = []
            for _, r in inv_df.iterrows():
                name = str(r.get("Name", "")).strip()
                if not name:
                    continue
                paco = pd.to_numeric(pd.Series([r.get("Paco", r.get("paco_w", 0))]), errors="coerce").fillna(0.0).iloc[0]
                vac = pd.to_numeric(pd.Series([r.get("Vac", r.get("vac", 0))]), errors="coerce").fillna(0.0).iloc[0]
                inv.append(
                    {
                        "name": name,
                        "manufacturer": (
                            name.split(":")[0].strip() if ":" in name else str(r.get("manufacturer", ""))
                        ),
                        "model": name.split(":", 1)[1].strip() if ":" in name else str(r.get("model", name)),
                        "paco_w": float(paco),
                        "vac": float(vac),
                    }
                )

            pv_json = out_dir / "pv_modules_online.json"
            inv_json = out_dir / "inverters_online.json"
            bat_json = out_dir / "battery_products_online.json"
            manifest_json = out_dir / "catalog_manifest.json"
            pv_json.write_text(json.dumps({"items": pv}, indent=2, ensure_ascii=False), encoding="utf-8")
            inv_json.write_text(json.dumps({"items": inv}, indent=2, ensure_ascii=False), encoding="utf-8")
            bat_json.write_text(json.dumps({"products": bat_products}, indent=2, ensure_ascii=False), encoding="utf-8")
            manifest_json.write_text(
            json.dumps(
                {
                    "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
                    "sources": {
                        "pv_modules_url": pv_url,
                        "inverters_url": inv_url,
                        "battery_products_url": bat_url,
                    },
                    "counts": {
                        "pv_modules": len(pv),
                        "inverters": len(inv),
                        "battery_products": len(bat_products),
                    },
                    "source_mode": source_mode,
                    "url_outage_detected": url_outage,
                    "warnings": warnings,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
            msg = "Catalog sync finished"
            if url_outage:
                msg = "Catalog sync finished with URL outage fallback"
            _log(f"Counts: pv={len(pv)}, inv={len(inv)}, bat={len(bat_products)}, url_outage={url_outage}")
            _log(f"Wrote outputs: {pv_json}, {inv_json}, {bat_json}, {manifest_json}")
            return OutputModel(
                message=msg,
                pv_catalog_json=str(pv_json),
                inverter_catalog_json=str(inv_json),
                battery_catalog_json=str(bat_json),
                catalog_manifest_json=str(manifest_json),
                url_outage_detected=url_outage,
            )
        except Exception as exc:
            (out_dir / "catalog_sync_error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            _log(f"ERROR during catalog sync: {exc}")
            raise
