from __future__ import annotations

import json
import math
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
try:
    from domino.base_piece import BasePiece
except ModuleNotFoundError:
    from local_compat.base_piece import BasePiece

from .models import InputModel, OutputModel


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def co2_tons_year(annual_pv_mwh: float, kg_co2_per_kwh: float = 0.57) -> float:
    return annual_pv_mwh * kg_co2_per_kwh


def simple_payback(capex: float, annual_savings: float) -> float:
    if annual_savings <= 0:
        return math.inf
    return capex / annual_savings


def npv_constant_savings(capex: float, annual_savings: float, years: int, discount_rate: float) -> float:
    if years <= 0:
        return -capex
    cashflows = [annual_savings / ((1.0 + discount_rate) ** year) for year in range(1, years + 1)]
    return -capex + sum(cashflows)


def sensitivity_matrix(
    capex: float,
    annual_savings: float,
    years: int,
    discount_rate: float,
    pct: float = 10.0,
) -> list[dict[str, Any]]:
    ratio = pct / 100.0
    rows: list[dict[str, Any]] = []
    scenarios = [
        ("Základ (simulácia alebo mriežka)", 1.0, 1.0),
        (f"Úspora -{pct:.0f} %", 1.0 - ratio, 1.0),
        (f"Úspora +{pct:.0f} %", 1.0 + ratio, 1.0),
        (f"CAPEX -{pct:.0f} %", 1.0, 1.0 - ratio),
        (f"CAPEX +{pct:.0f} %", 1.0, 1.0 + ratio),
    ]
    for label, savings_mul, capex_mul in scenarios:
        savings = max(0.0, annual_savings * savings_mul)
        cap = max(0.0, capex * capex_mul)
        payback = simple_payback(cap, savings)
        rows.append(
            {
                "scenario": label,
                "payback_years": round(payback, 2) if math.isfinite(payback) else None,
                "npv_eur": round(npv_constant_savings(cap, savings, years, discount_rate), 0),
                "capex_eur": round(cap, 0),
                "annual_savings_eur": round(savings, 0),
            }
        )
    return rows


def _load_catalog_items(path: Path, list_key: str) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get(list_key) if isinstance(payload, dict) else None
    return items if isinstance(items, list) else []


def recommend_pv_system(
    target_kwp: float,
    modules: list[dict[str, Any]] | None = None,
    *,
    constraints: dict[str, Any] | None = None,
    economics: dict[str, Any] | None = None,
    selection_strategy: str | None = None,
    reference_wp: float | None = None,
) -> dict[str, Any]:
    del constraints, economics
    modules = modules or _load_catalog_items(project_root() / "catalog" / "pv_modules_catalog.json", "modules")
    if not modules:
        return {"error": "Prázdny katalóg panelov"}

    strategy = selection_strategy or "max_power_wp"
    ref_wp = float(reference_wp or 300.0)
    if strategy == "closest_to_reference_wp":
        chosen = min(modules, key=lambda item: abs(float(item.get("power_wp", 0.0)) - ref_wp))
    else:
        chosen = max(
            modules,
            key=lambda item: (
                float(item.get("power_wp", 0.0)),
                float(item.get("efficiency_pct", 0.0)),
                -float(item.get("eur_per_wp", 999.0)),
            ),
        )

    power_wp = max(1.0, float(chosen.get("power_wp", 0.0)))
    module_count = max(0, int(round(target_kwp * 1000.0 / power_wp))) if target_kwp > 0 else 0
    installed_kwp = module_count * power_wp / 1000.0
    return {
        "catalog_module_count": len(modules),
        "catalog_source": "catalog/pv_modules_catalog.json",
        "module_manufacturer": chosen.get("manufacturer"),
        "module_model": chosen.get("model"),
        "sam_key": chosen.get("sam_key"),
        "cec_key": chosen.get("cec_key"),
        "module_power_wp": power_wp,
        "module_count": module_count,
        "installed_kwp_dc_approx": round(installed_kwp, 2),
        "selection_mode": "local_catalog",
        "selection_strategy_used": strategy,
        "catalog_note": chosen.get("note"),
    }


def recommend_battery_system(target_kwh: float, products: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if target_kwh <= 0:
        return {
            "product_id": None,
            "manufacturer": None,
            "model_label": None,
            "units": 0,
            "nominal_kwh_installed": 0.0,
            "source": "catalog/battery_catalog.json",
        }
    products = products or _load_catalog_items(project_root() / "catalog" / "battery_catalog.json", "products")
    if not products:
        return {"error": "Prázdny katalóg batérií"}

    sorted_products = sorted(products, key=lambda item: float(item.get("nominal_kwh", 0.0)))
    chosen = next(
        (item for item in sorted_products if float(item.get("nominal_kwh", 0.0)) >= target_kwh),
        sorted_products[-1],
    )
    nominal_per_unit = max(1.0, float(chosen.get("nominal_kwh", 0.0)))
    units = max(1, int(math.ceil(target_kwh / nominal_per_unit)))
    nominal_total = nominal_per_unit * units
    return {
        "product_id": chosen.get("id"),
        "manufacturer": chosen.get("manufacturer"),
        "product_line": chosen.get("product_line"),
        "model_label": f"{chosen.get('manufacturer')} - {chosen.get('product_line')}",
        "chemistry": chosen.get("chemistry"),
        "form_factor": chosen.get("form_factor"),
        "units": units,
        "nominal_kwh_per_unit": nominal_per_unit,
        "nominal_kwh_installed": round(nominal_total, 1),
        "max_power_kw_note": chosen.get("max_power_kw"),
        "catalog_product_count": len(products),
        "source": "catalog/battery_catalog.json (verify with supplier)",
    }


def verify_cec_key_exists(cec_key: str) -> bool:
    if not cec_key:
        return False
    try:
        from pvlib import pvsystem

        return cec_key in pvsystem.retrieve_sam("CECMod").columns
    except Exception:
        return False


def verify_sam_key_exists(sam_key: str) -> bool:
    if not sam_key:
        return False
    try:
        from pvlib import pvsystem

        return sam_key in pvsystem.retrieve_sam("SandiaMod").columns
    except Exception:
        return False


def verify_module_keys_for_simulation(sam_key: str | None, cec_key: str | None) -> tuple[bool, str | None]:
    if cec_key and verify_cec_key_exists(cec_key):
        return True, None
    if sam_key and verify_sam_key_exists(sam_key):
        return True, None
    if cec_key or sam_key:
        return False, "Kľúč modulu nie je v CECMod ani v SandiaMod (pvlib)."
    return False, "Chýba sam_key aj cec_key pre overenie voči pvlib."


class FeasibilityReportPiece(BasePiece):
    """Porovná výsledok s cieľovou payback; doplní text pre CFO a uloží JSON."""

    def _output_dir(self) -> Path:
        rp = getattr(self, "results_path", None)
        if rp:
            return Path(rp)
        return project_root() / "tests" / "FeasibilityReportPiece_Outputs"

    def piece_function(self, input_data: InputModel) -> OutputModel:
        out_dir = self._output_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        log_path = out_dir / "feasibility_report.log"
        err_path = out_dir / "feasibility_report_error.txt"
        try:
            c = input_data.constraints
            e = input_data.economics
            fin = e.get("finance") or {}
            years = int(fin.get("analysis_years", 15))
            dr = float(fin.get("discount_rate", 0.08))
            sens_pct = float(e.get("electricity", {}).get("price_sensitivity_pct", 10))

            target = float(c.get("target_payback_years", 99))
            grid = input_data.grid
            finite_pbs = [row["payback_years"] for row in grid if row.get("payback_years") is not None]
            min_pb = min(finite_pbs) if finite_pbs else None

            parametric_pb = float(input_data.best_payback_years)
            parametric_sav = float(input_data.best_annual_savings_eur)
            parametric_npv = float(input_data.best_npv_eur)
            parametric_capex = float(input_data.best_capex_eur)

            sim = input_data.simulation_metrics
            if sim and sim.get("annual_savings_eur") is not None:
                achieved_pb = float(sim["simple_payback_years"])
                achieved_sav = float(sim["annual_savings_eur"])
                achieved_npv = float(sim["npv_eur"])
                capex_use = float(sim.get("total_capex_eur", parametric_capex))
                model_basis = "timeseries_simulation"
                feasible = math.isfinite(achieved_pb) and achieved_pb > 0 and achieved_pb <= target + 1e-6
                msg = (
                    f"Cieľová návratnosť **{target} r.**: {'**SPLNITEĽNÉ**' if feasible else '**NESPLNITEĽNÉ**'} "
                    f"podľa **časovej simulácie** (KPI → InvestmentEval). "
                    f"Payback **{achieved_pb:.2f} r.** | ročná úspora **{achieved_sav:,.0f} €**. "
                    f"Mriežkový odhad (pred simuláciou) bol payback **{parametric_pb:.2f} r.** "
                    f"({input_data.best_kwp:.0f} kWp + {input_data.best_kwh:.0f} kWh)."
                )
                if not feasible and min_pb is not None:
                    msg += f" Min. payback v prehľadávanej mriežke (orientačný): **{min_pb:.2f} r.**"
            else:
                achieved_pb = parametric_pb
                achieved_sav = parametric_sav
                achieved_npv = parametric_npv
                capex_use = parametric_capex
                model_basis = "parametric_grid_only"
                feasible = math.isfinite(achieved_pb) and achieved_pb > 0 and achieved_pb <= target + 1e-6
                if not finite_pbs:
                    feasible = False
                msg = (
                    f"Cieľová návratnosť {target} r.: {'SPLNITEĽNÉ' if feasible else 'NESPLNITEĽNÉ'}. "
                    f"Najlepší návrh v mriežke: {input_data.best_kwp:.0f} kWp, {input_data.best_kwh:.0f} kWh, "
                    f"payback {achieved_pb:.2f} r. (parametrický model, bez časovej simulácie v tomto behu)."
                )
                if not feasible and min_pb is not None:
                    msg += f" Minimálna dosiahnuteľná návratnosť (v mriežke): {min_pb:.2f} r."

            solar = e.get("solar", {})
            yield_kwp = float(solar.get("yield_kwh_per_kwp_year", 1000))
            annual_pv_mwh = input_data.best_kwp * yield_kwp / 1000.0
            kg = float(e.get("emissions", {}).get("kg_co2_per_kwh_grid", 0.57))
            if sim and sim.get("annual_co2_saved_ton") is not None:
                co2_tons = float(sim["annual_co2_saved_ton"])
            else:
                co2_tons = co2_tons_year(annual_pv_mwh, kg)

            pv_hw = recommend_pv_system(input_data.best_kwp, constraints=c, economics=e)
            batt_hw = recommend_battery_system(input_data.best_kwh)
            ok_key, key_msg = verify_module_keys_for_simulation(pv_hw.get("sam_key"), pv_hw.get("cec_key"))
            if not ok_key:
                pv_hw["sam_verify_warning"] = key_msg or "Modul bez platného kľúča v pvlib (CEC/Sandia)."
            elif pv_hw.get("cec_key") and not pv_hw.get("sam_key"):
                pv_hw["sam_verify_note"] = (
                    "Modul má CEC kľúč (vhodné pre novšie API); SolarSimPiece v tomto projekte defaultne očakáva "
                    "``module_name`` z SandiaMod v solar_config.yml – pre zhodu profilu zvoľ rovnaký typ."
                )

            sens_rows = sensitivity_matrix(capex_use, achieved_sav, years, dr, pct=sens_pct)
            cfo = {
                "scenario_summary": msg,
                "sensitivity_matrix": sens_rows,
                "sensitivity_hint": (
                    "Tabuľka: šoky ± na ročnej úspore a CAPEX (orientačné). "
                    "Detailnejšiu tarifu doplň v vstupoch / časovej simulácii."
                ),
                "estimated_co2_avoided_tons_year": round(co2_tons, 2),
                "npv_eur_at_best": round(achieved_npv, 2),
                "recommended_pv_hardware": pv_hw,
                "recommended_battery_hardware": batt_hw,
                "assumptions": self._assumptions_list(model_basis == "timeseries_simulation"),
            }
            parametric_block = {
                "payback_years": round(parametric_pb, 3) if math.isfinite(parametric_pb) else None,
                "annual_savings_eur": round(parametric_sav, 2),
                "npv_eur": round(parametric_npv, 2),
                "capex_eur": round(parametric_capex, 2),
                "label": "Parametrická mriežka (pieces/kit/economics – pred časovou simuláciou)",
            }

            out = {
                "model_basis": model_basis,
                "feasible": feasible,
                "target_payback_years": target,
                "recommended_kwp": input_data.best_kwp,
                "recommended_kwh": input_data.best_kwh,
                "achieved_payback_years": achieved_pb if math.isfinite(achieved_pb) else None,
                "minimum_payback_in_search_space_years": min_pb,
                "annual_savings_eur": round(achieved_sav, 2),
                "capex_eur": round(capex_use, 2),
                "parametric_estimate": parametric_block,
                "simulation": sim,
                "cfo_notes": cfo,
                "hardware": {"pv": pv_hw, "battery": batt_hw},
            }
            (out_dir / "feasibility_report.json").write_text(
                json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
            )
            flat = {k: out[k] for k in out if k not in ("cfo_notes", "simulation", "parametric_estimate")}
            pd.DataFrame([flat]).to_csv(out_dir / "feasibility_summary.csv", index=False)
            if grid:
                pd.DataFrame(grid).to_csv(out_dir / "sizing_grid.csv", index=False)

            dashboard_payload = {
                "meta": {
                    "workflow": "alternate_sizing",
                    "model_basis": model_basis,
                    "site_name": c.get("site_name", ""),
                    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                },
                "feasibility": out,
                "cfo_notes": cfo,
                "sizing_grid": grid,
            }
            (out_dir / "dashboard_data.json").write_text(
                json.dumps(dashboard_payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
            )
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("[INFO] FeasibilityReportPiece completed\n")
            return OutputModel(
                feasible=feasible,
                target_payback_years=target,
                recommended_kwp=input_data.best_kwp,
                recommended_kwh=input_data.best_kwh,
                achieved_payback_years=achieved_pb if math.isfinite(achieved_pb) else -1.0,
                minimum_payback_in_search_space_years=min_pb if min_pb is not None else -1.0,
                message=msg,
                cfo_notes=cfo,
            )
        except Exception:
            err = traceback.format_exc()
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("[ERROR] FeasibilityReportPiece failed\n")
                f.write(err + "\n")
            with open(err_path, "w", encoding="utf-8") as f:
                f.write(err)
            raise

    @staticmethod
    def _assumptions_list(had_simulation: bool) -> list[str]:
        base = [
            "CAPEX z jednotkových cien (economics_defaults / investment_config); payback = jednoduchý CAPEX / ročná úspora.",
            "Panely: katalóg + SAM/pvlib; batérie: orientačné produkty v catalog/battery_catalog.json.",
        ]
        if had_simulation:
            return [
                "Ročná úspora a payback v hlavnom súhrne sú z **časovej simulácie** (KPIPiece → InvestmentEvalPiece), nie z mriežky.",
                "Parametrický riadok zostáva ako porovnanie (rýchly odhad pred simuláciou).",
            ] + base
        return [
            "Tento beh neobsahuje časovú simuláciu – čísla sú z **parametrickej mriežky**.",
            "Pre úspory z 15 min dát spusti: `python run_workflow.py` (celý pipeline).",
        ] + base
