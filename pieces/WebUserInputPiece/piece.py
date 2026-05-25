from __future__ import annotations

import json
import traceback
from pathlib import Path

from domino.base_piece import BasePiece

from pieces.UserInputPiece.models import InputModel as ClassicInput
from pieces.UserInputPiece.piece import UserInputPiece


from .models import FIELD_LABELS, H, InputModel, OutputModel


class WebUserInputPiece(BasePiece):
    """
    Web-based user input: materialize JSON/YAML/CSV from Streamlit form state,
    then validate via the same logic as UserInputPiece (classic CSV path).
    """

    def piece_function(self, input_data: InputModel) -> OutputModel:
        out_dir = Path(self.results_path or Path(__file__).resolve().parents[2] / "tests" / "UserInputPiece_Output")
        out_dir.mkdir(parents=True, exist_ok=True)
        log_path = out_dir / "web_user_input.log"

        def _log(msg: str) -> None:
            text = f"[WebUserInputPiece] {msg}"
            print(text, flush=True)
            with log_path.open("a", encoding="utf-8") as f:
                f.write(text + "\n")

        try:
            state_path = Path(input_data.web_form_state_json)
            if not state_path.is_file():
                raise FileNotFoundError(
                    f"Missing {state_path}. Run: python -m streamlit run scripts/streamlit_web_input.py "
                    "and click Save, or copy web_form_state.json into WebUserInputPiece_Input."
                )
            state = load_state(state_path)
            save_state(state_path, state)
            paths = materialize_from_state(state, use_classic_fallback=input_data.use_classic_csv_fallback)
            _log(f"Materialized workflow_user_input: {paths['workflow_user_input_json']}")
            _log(f"Load CSV: {paths['load_csv']}")

            scenario_path = Path(input_data.scenario_yaml)
            if not scenario_path.is_file():
                from workflow import paths as P

                scenario_path = P.GENERATED_SCENARIO_YML

            classic = UserInputPiece.__new__(UserInputPiece)
            classic.results_path = str(out_dir)
            classic_out = classic.piece_function(
                ClassicInput(
                    load_csv=paths["load_csv"],
                    prices_csv=paths.get("prices_csv") or "",
                    scenario_yaml=str(scenario_path),
                )
            )

            summary_path = out_dir / "web_user_input_summary.json"
            summary_path.write_text(
                json.dumps(
                    {
                        "input_mode": "web",
                        "materialized": paths,
                        "validated": classic_out.model_dump(),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            return OutputModel(
                message="Web user input materialized and validated",
                load_csv=classic_out.load_csv,
                scenario_yaml=classic_out.scenario_yaml,
                workflow_user_input_json=paths["workflow_user_input_json"],
                web_form_state_json=str(state_path),
                input_mode="web",
            )
        except Exception:
            err = traceback.format_exc()
            with log_path.open("a", encoding="utf-8") as f:
                f.write("[ERROR]\n" + err)
            raise

# --- form I/O (web state) ---
"""
Load/save web form state and materialize workflow_user_input.json + scenario.yaml + CSV paths.
"""


import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

WEB_FORM_FORMAT = "web_user_input_v1"
WORKFLOW_FORMAT = "workflow_user_input_v1"

# Jediný zdroj pravdy pre „čo simulovať“ (project_options sa z toho odvodí pri uložení).
SYSTEM_SCOPE_OPTIONS: dict[str, str] = {
    "pv_and_battery": "FVE + batéria",
    "pv_only": "Len FVE",
    "battery_only": "Len batéria",
}


def sync_scope_from_state(state: dict[str, Any]) -> str:
    """Read equipment.system_scope and mirror to project_options + use_pv/use_battery flags."""
    equip = (state.get("scenario") or {}).get("equipment") or {}
    scope = str(equip.get("system_scope") or "pv_and_battery").strip().lower()
    if scope not in SYSTEM_SCOPE_OPTIONS:
        scope = "pv_and_battery"
        equip["system_scope"] = scope
    po = state.setdefault("project_options", {})
    po["include_solar_pv"] = scope in ("pv_and_battery", "pv_only")
    po["include_battery"] = scope in ("pv_and_battery", "battery_only")
    scen = state.setdefault("scenario", {})
    if scope in ("pv_only", "pv"):
        scen["use_pv"], scen["use_battery"] = True, False
    elif scope in ("battery_only", "battery"):
        scen["use_pv"], scen["use_battery"] = False, True
    else:
        scen["use_pv"], scen["use_battery"] = True, True
    return scope


def sync_project_options_to_scope(state: dict[str, Any]) -> None:
    """Legacy: if only project_options checkboxes were set, map to system_scope (prefer explicit scope)."""
    equip = (state.get("scenario") or {}).get("equipment") or {}
    if equip.get("system_scope"):
        sync_scope_from_state(state)
        return
    po = state.get("project_options") or {}
    pv = bool(po.get("include_solar_pv", True))
    bat = bool(po.get("include_battery", True))
    if pv and bat:
        equip["system_scope"] = "pv_and_battery"
    elif pv:
        equip["system_scope"] = "pv_only"
    elif bat:
        equip["system_scope"] = "battery_only"
    else:
        equip["system_scope"] = "pv_and_battery"
    sync_scope_from_state(state)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, val in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def _infer_dt_hours(df: pd.DataFrame) -> float:
    if "datetime" not in df.columns:
        return 0.25
    dt = pd.to_datetime(df["datetime"], errors="coerce")
    delta = dt.diff().dt.total_seconds().median() / 3600.0
    return float(delta) if pd.notna(delta) and delta > 0 else 0.25


def annual_load_mwh_from_csv(csv_path: Path) -> float | None:
    """Odhad ročnej spotreby z časovej rady load_kw (extrapolácia na 365 dní)."""
    if not csv_path.is_file():
        return None
    try:
        df = pd.read_csv(csv_path, sep=None, engine="python")
    except Exception:
        return None
    if "load_kw" in df.columns:
        load = pd.to_numeric(df["load_kw"], errors="coerce")
    else:
        num = df.select_dtypes(include="number")
        if num.empty:
            return None
        load = pd.to_numeric(num.iloc[:, 0], errors="coerce")
    load = load.dropna()
    if load.empty:
        return None
    dt_h = _infer_dt_hours(df)
    days = len(load) * dt_h / 24.0
    raw_mwh = float(load.sum() * dt_h / 1000.0)
    return raw_mwh * (365.0 / max(days, 1e-6))


def _resolve_load_csv_path(state: dict[str, Any], *, use_classic_fallback: bool = False) -> Path | None:
    from workflow import paths as P

    data = state.get("data") or {}
    load_raw = str(data.get("load_csv") or "").strip()
    load_path = Path(load_raw) if load_raw else P.WEB_UPLOAD_LOAD_CSV
    if load_path.is_file():
        return load_path
    if use_classic_fallback:
        try:
            load_path, _ = resolve_load_and_prices_paths(state, use_classic_fallback=True)
            return load_path
        except FileNotFoundError:
            pass
    return None


def _read_load_dataframe(csv_path: Path) -> pd.DataFrame | None:
    try:
        from pieces.TechnicalLimitsPiece.piece import _load_consumption_csv

        return _load_consumption_csv(csv_path)
    except Exception:
        return None


def timestep_minutes_from_csv(csv_path: Path) -> int | None:
    df = _read_load_dataframe(csv_path)
    if df is None or len(df) < 2:
        return None
    from pieces.TechnicalLimitsPiece.piece import _infer_timestep_hours

    return max(1, int(round(_infer_timestep_hours(df) * 60)))


def suggest_mrk_contract_kw_from_csv(csv_path: Path) -> float | None:
    """Najvyšší mesačný peak odberu (kW) — orientačný RV, ak nie je v zmluve inak."""
    df = _read_load_dataframe(csv_path)
    if df is None or df.empty:
        return None
    df = df.copy()
    df["month"] = df["datetime"].dt.to_period("M")
    monthly = df.groupby("month")["load_kw"].max()
    if monthly.empty:
        return float(df["load_kw"].max())
    return float(monthly.max())


def csv_has_price_column(csv_path: Path) -> bool:
    try:
        df = pd.read_csv(csv_path, sep=None, engine="python", nrows=5)
    except Exception:
        return False
    cols = {c.strip().lower().replace(" ", "_") for c in df.columns}
    return bool(
        cols
        & {
            "price_eur_per_kwh",
            "price_eur_kwh",
            "price_eur_mwh",
        }
    )


def estimate_bounds_from_state(state: dict[str, Any], csv_path: Path) -> dict[str, float] | None:
    df = _read_load_dataframe(csv_path)
    if df is None:
        return None
    from pieces.TechnicalLimitsPiece.piece import _infer_timestep_hours, _technical_bounds_kwp_kwh

    constraints = state.get("constraints") or {}
    economics = state.get("economics") or {}
    layout = economics.get("layout") or {}
    solar = economics.get("solar") or {}
    battery = economics.get("battery") or {}
    install = constraints.get("installation") or {}
    cfg = {
        "equipment": {
            "constraints": constraints,
            "layout": {
                "kwp_per_m2_roof": layout.get("kwp_per_m2_roof", 0.18),
                "kwh_per_m2_battery_area": layout.get("kwh_per_m2_battery_area", 2.5),
            },
        },
        "pv": {
            "yield_kwh_per_kwp_year": solar.get("yield_kwh_per_kwp_year", 1000.0),
            "specific_capex_eur_per_kwp": solar.get("eur_per_kwp", 900.0),
        },
        "battery": {"specific_capex_eur_per_kwh": battery.get("eur_per_kwh", 350.0)},
    }
    dt_h = _infer_timestep_hours(df)
    b = _technical_bounds_kwp_kwh(cfg, df, dt_h)
    return {
        "max_kwp": float(b["max_kwp"]),
        "max_kwh": float(b["max_kwh"]),
        "annual_load_mwh_est": float(b["annual_load_mwh_est"]),
    }


def sync_derived_fields(state: dict[str, Any]) -> None:
    """Zjednotí duplicitné hodnoty medzi záložkami (ekonomika → scenár, site → solar_config)."""
    economics = state.get("economics") or {}
    solar_econ = economics.get("solar") or {}
    batt_econ = economics.get("battery") or {}
    scen = state.setdefault("scenario", {})
    pv = scen.setdefault("pv", {})
    bat = scen.setdefault("battery", {})
    if solar_econ.get("yield_kwh_per_kwp_year") is not None:
        pv["yield_kwh_per_kwp_year"] = solar_econ["yield_kwh_per_kwp_year"]
    if solar_econ.get("eur_per_kwp") is not None:
        pv["specific_capex_eur_per_kwp"] = solar_econ["eur_per_kwp"]
    if batt_econ.get("eur_per_kwh") is not None:
        bat["specific_capex_eur_per_kwh"] = batt_econ["eur_per_kwh"]
    site = (state.get("constraints") or {}).get("site") or {}
    sc = state.setdefault("solar_config", {})
    if site.get("latitude") is not None:
        sc["site_latitude"] = site["latitude"]
    if site.get("longitude") is not None:
        sc["site_longitude"] = site["longitude"]


def sync_from_csv(state: dict[str, Any], *, use_classic_fallback: bool = False) -> dict[str, Any]:
    """
    Doplní z CSV všetko, čo vieme odvodiť (krok času, ročná spotreba, návrh RV, max. mriežka).
    Vráti slovník hintov pre UI (čo sa zobrazí používateľovi).
    """
    hints: dict[str, Any] = {}
    load_path = _resolve_load_csv_path(state, use_classic_fallback=use_classic_fallback)
    if load_path is None:
        return hints

    sync_annual_load_constraint(state, use_classic_fallback=use_classic_fallback)
    constraints = state.setdefault("constraints", {})
    if constraints.get("annual_load_mwh") is not None:
        hints["annual_load_mwh"] = constraints["annual_load_mwh"]

    scen = state.setdefault("scenario", {})
    mins = timestep_minutes_from_csv(load_path)
    if mins is not None and scen.get("timestep_minutes_from") != "manual":
        scen["timestep_minutes"] = mins
        scen["timestep_minutes_from"] = "csv"
        hints["timestep_minutes"] = mins

    peak = suggest_mrk_contract_kw_from_csv(load_path)
    if peak is not None:
        hints["mrk_peak_kw"] = round(peak, 1)
        mrk = scen.setdefault("mrk", {})
        mrk["suggested_contract_kw"] = round(peak, 1)

    if csv_has_price_column(load_path):
        hints["prices_in_load_csv"] = True

    bounds = estimate_bounds_from_state(state, load_path)
    if bounds:
        hints["bounds"] = bounds
        equip = scen.setdefault("equipment", {})
        auto = equip.setdefault("auto", {})
        gs = auto.setdefault("grid_sweep", {})
        if gs.get("grid_bounds_from") != "manual":
            gs["kwp_max"] = round(bounds["max_kwp"], 0)
            gs["kwh_max"] = round(bounds["max_kwh"], 0)
            gs["grid_bounds_from"] = "csv"

    sync_derived_fields(state)
    return hints


def sync_annual_load_constraint(state: dict[str, Any], *, use_classic_fallback: bool = False) -> bool:
    """
    Ak je nahratý CSV so spotrebou, nastaví constraints.annual_load_mwh z dát.
    Vráti True, ak hodnota pochádza z CSV (simulácia aj tak používa celú časovú radu).
    """
    load_path = _resolve_load_csv_path(state, use_classic_fallback=use_classic_fallback)
    if load_path is None:
        constraints = state.setdefault("constraints", {})
        constraints.setdefault("annual_load_mwh_from", "manual")
        return False
    est = annual_load_mwh_from_csv(load_path)
    constraints = state.setdefault("constraints", {})
    if est is not None:
        constraints["annual_load_mwh"] = round(est, 3)
        constraints["annual_load_mwh_from"] = "csv"
        return True
    constraints.setdefault("annual_load_mwh_from", "manual")
    return False


def default_state() -> dict[str, Any]:
    """Bootstrap from existing workflow JSON / scenario template when present."""
    from workflow import paths as P

    state: dict[str, Any] = {
        "format": WEB_FORM_FORMAT,
        "saved_at_utc": None,
        "project_options": {"include_solar_pv": True, "include_battery": True},
        "constraints": {
            "site_name": "Demo plant",
            "site": {"latitude": 48.17, "longitude": 17.07, "country": "SK"},
            "installation": {
                "mount_type": "roof",
                "roof_shape": "pitched",
                "roof_tilt_deg": 15,
                "orientation_deg": 180,
                "shading": "low",
                "priority": "balanced",
                "allow_bifacial": True,
                "notes": "",
            },
            "target_payback_years": 8.0,
            "max_roof_area_m2": 8000.0,
            "max_ground_area_m2": 0.0,
            "max_battery_area_m2": 400.0,
            "annual_load_mwh": 1200.0,
            "min_pv_kwp": 0.0,
            "roof_load_limit_kg_per_m2": 120.0,
            "max_capex_eur": 0.0,
            "search": {"kwp_step": 50, "kwh_step": 25, "kwp_min": 0, "kwh_min": 0},
        },
        "economics": {
            "currency": "EUR",
            "solar": {
                "eur_per_kwp": 900.0,
                "yield_kwh_per_kwp_year": 1000.0,
                "self_consumption_base": 0.45,
            },
            "battery": {"eur_per_kwh": 350.0, "peak_shaving_value_eur_per_kwh_year": 25.0},
            "electricity": {"price_sensitivity_pct": 10.0},
            "finance": {
                "discount_rate": 0.08,
                "analysis_years": 15,
                "degradation_solar_per_year": 0.005,
            },
            "emissions": {"kg_co2_per_kwh_grid": 0.57},
            "layout": {
                "kwp_per_m2_roof": 0.18,
                "kwh_per_m2_battery_area": 2.5,
                "roof_additional_load_kg_per_m2_max": 25.0,
            },
        },
        "scenario": {
            "timezone": "Europe/Bratislava",
            "timestep_minutes": 15,
            "use_pv": True,
            "use_battery": True,
            "mrk": {
                "contract_kw": 420.0,
                "fee_eur_per_kw_month": 4.85,
                "excess_peak_penalty_eur_per_kw": 32.0,
                "rv_downsizing_safety_margin_pct": 8.0,
            },
            "analysis": {
                "amortization_years": 15,
                "discount_rate": 0.08,
                "enable_trading_only_scenario": True,
                "enable_c_rate_sweep": True,
                "c_rate_sweep_values": [0.25, 0.5, 1.0],
            },
            "finance": {
                "enabled": True,
                "o_and_m_pct_of_capex": 1.5,
                "debt_ratio_of_capex": 0.6,
                "debt_interest_rate": 0.05,
                "debt_years": 10,
                "tax_rate_pct": 21,
            },
            "pv": {
                "installed_kwp": 400.0,
                "specific_capex_eur_per_kwp": 900.0,
                "yield_kwh_per_kwp_year": 1000.0,
            },
            "battery": {
                "energy_kwh": 200.0,
                "max_c_rate": 0.5,
                "charge_efficiency": 0.95,
                "discharge_efficiency": 0.95,
                "specific_capex_eur_per_kwh": 350.0,
            },
            "equipment": {
                "selection_mode": "auto",
                "system_scope": "pv_and_battery",
                "auto": {
                    "objective": "max_npv",
                    "target_payback_years": 8,
                    "kwp_step": 50,
                    "kwh_step": 50,
                    "min_pv_kwp": 100,
                    "min_battery_kwh": 100,
                    "max_configurations": 180,
                    "grid_sweep": {
                        "kwp_min": 100,
                        "kwp_max": 500,
                        "kwp_step": 50,
                        "kwh_min": 50,
                        "kwh_max": 300,
                        "kwh_step": 50,
                        "respect_physical_bounds": False,
                    },
                },
            },
        },
        "solar_config": {
            "tilt": 35,
            "azimuth": 180,
            "site_latitude": 48.17,
            "site_longitude": 17.07,
            "efficiency": 0.9,
        },
        "investment_eval": {
            "analysis_years": 20,
            "discount_rate": 0.05,
            "degradation_per_year": 0.006,
        },
        "battery_config": {
            "charge_efficiency": 0.95,
            "discharge_efficiency": 0.95,
            "max_c_rate": 0.5,
            "initial_soc": 50,
        },
        "data": {
            "load_csv": "",
            "prices_csv": "",
            "append_new_rows_to_company_drop": True,
        },
    }

    if P.WORKFLOW_USER_INPUT_JSON.is_file():
        wf = json.loads(P.WORKFLOW_USER_INPUT_JSON.read_text(encoding="utf-8"))
        state["project_options"] = wf.get("project_options") or state["project_options"]
        uip = wf.get("UserInputPiece") or {}
        if uip.get("constraints"):
            state["constraints"] = _deep_merge(state["constraints"], uip["constraints"])
        if uip.get("economics"):
            state["economics"] = _deep_merge(state["economics"], uip["economics"])
        batt = wf.get("BatterySimPiece") or {}
        if isinstance(batt.get("scenario"), dict):
            state["scenario"] = _deep_merge(state["scenario"], batt["scenario"])
        if isinstance(batt.get("battery_config"), dict):
            state["battery_config"] = _deep_merge(state["battery_config"], batt["battery_config"])
        solar = wf.get("SolarSimPiece") or {}
        if isinstance(solar.get("solar_config"), dict):
            state["solar_config"] = _deep_merge(state["solar_config"], solar["solar_config"])
        if isinstance(wf.get("InvestmentEvalPiece"), dict):
            state["investment_eval"] = _deep_merge(state["investment_eval"], wf["InvestmentEvalPiece"])

    if P.USER_SCENARIO_YML.is_file():
        scen = yaml.safe_load(P.USER_SCENARIO_YML.read_text(encoding="utf-8")) or {}
        for key in ("timezone", "timestep_minutes", "use_pv", "use_battery", "mrk", "analysis", "finance", "equipment", "production"):
            if key in scen:
                if isinstance(scen[key], dict) and isinstance(state["scenario"].get(key), dict):
                    state["scenario"][key] = _deep_merge(state["scenario"].get(key, {}), scen[key])
                else:
                    state["scenario"][key] = scen[key]

    if P.WEB_UPLOAD_LOAD_CSV.is_file():
        state["data"]["load_csv"] = str(P.WEB_UPLOAD_LOAD_CSV)
    if P.WEB_UPLOAD_PRICES_CSV.is_file():
        state["data"]["prices_csv"] = str(P.WEB_UPLOAD_PRICES_CSV)
    return state


def load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        state = default_state()
        sync_scope_from_state(state)
        return state
    data = json.loads(path.read_text(encoding="utf-8"))
    base = default_state()
    merged = _deep_merge(base, data)
    sync_scope_from_state(merged)
    return merged


def save_state(path: Path, state: dict[str, Any]) -> None:
    state = dict(state)
    sync_scope_from_state(state)
    sync_from_csv(state, use_classic_fallback=True)
    state["format"] = WEB_FORM_FORMAT
    state["saved_at_utc"] = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def build_workflow_user_input_json(state: dict[str, Any]) -> dict[str, Any]:
    sync_scope_from_state(state)
    sync_from_csv(state, use_classic_fallback=True)
    scen = state.get("scenario") or {}
    equip = scen.get("equipment") or {}
    auto = equip.get("auto") or {}
    constraints = state.get("constraints") or {}
    target_pb = float(constraints.get("target_payback_years", 8.0))
    auto.setdefault("target_payback_years", target_pb)
    search = constraints.get("search") or {}
    auto.setdefault("kwp_step", search.get("kwp_step", 50))
    auto.setdefault("kwh_step", search.get("kwh_step", 25))
    equip.setdefault("auto", auto)
    scen["equipment"] = equip

    batt_scenario = {
        "scenario_id": "workflow",
        "description": "From WebUserInputPiece",
        "equipment": equip,
        "solar": {"capacity_kWp": 0.0},
        "battery": {
            "capacity_kWh": 0.0,
            "charge_efficiency": (state.get("battery_config") or {}).get("charge_efficiency", 0.95),
            "discharge_efficiency": (state.get("battery_config") or {}).get("discharge_efficiency", 0.95),
            "max_c_rate": (state.get("battery_config") or {}).get("max_c_rate", 0.5),
        },
        "strategy": scen.get("strategy")
        or {
            "charge_from": "solar_excess",
            "discharge_during": "peak_hours",
        },
        "time_window": scen.get("time_window")
        or {"peak_hours": {"start": "08:00", "end": "18:00"}},
        "apply_monthly": scen.get("apply_monthly", True),
    }
    for key in ("mrk", "analysis", "finance", "pv", "battery", "energy", "production"):
        if key in scen:
            batt_scenario[key] = scen[key]

    mode = str(equip.get("selection_mode", "auto")).lower()
    pv_block = batt_scenario.get("pv") or {}
    bat_block = batt_scenario.get("battery") or {}
    if mode == "manual":
        kwp = float(pv_block.get("installed_kwp", 0.0))
        kwh = float(bat_block.get("energy_kwh", bat_block.get("capacity_kWh", 0.0)))
        batt_scenario["solar"] = {"capacity_kWp": kwp}
        batt_scenario["battery"]["capacity_kWh"] = kwh
        batt_scenario["battery"]["energy_kwh"] = kwh

    return {
        "format": WORKFLOW_FORMAT,
        "project_options": state.get("project_options") or {},
        "UserInputPiece": {
            "constraints": constraints,
            "economics": state.get("economics") or {},
        },
        "SolarSimPiece": {"solar_config": state.get("solar_config") or {}},
        "InvestmentEvalPiece": state.get("investment_eval") or {},
        "BatterySimPiece": {
            "scenario": batt_scenario,
            "battery_config": state.get("battery_config") or {},
        },
    }


def build_scenario_yaml(state: dict[str, Any]) -> dict[str, Any]:
    from workflow.user_input import _load_user_scenario_template

    base = _load_user_scenario_template()
    scen = state.get("scenario") or {}
    merged = _deep_merge(base, scen)
    merged.setdefault("strategy", {"charge_from": "solar_excess", "discharge_during": "peak_hours"})
    merged.setdefault("time_window", {"peak_hours": {"start": "08:00", "end": "18:00"}})
    merged.setdefault("apply_monthly", True)
    merged.setdefault("solar", {"capacity_kWp": 0.0})
    merged.setdefault("battery", {"capacity_kWh": 0.0, "energy_kwh": 0.0})
    pv_block = merged.get("pv") or {}
    bat_block = merged.get("battery") or {}
    kwp = float(pv_block.get("installed_kwp", merged["solar"].get("capacity_kWp", 0.0)))
    kwh = float(bat_block.get("energy_kwh", bat_block.get("capacity_kWh", merged["battery"].get("energy_kwh", 0.0))))
    if kwp > 0:
        merged["solar"]["capacity_kWp"] = kwp
        pv_block["installed_kwp"] = kwp
        merged["pv"] = pv_block
    if kwh > 0:
        merged["battery"]["capacity_kWh"] = kwh
        merged["battery"]["energy_kwh"] = kwh
    return merged


def resolve_load_and_prices_paths(
    state: dict[str, Any],
    *,
    use_classic_fallback: bool,
) -> tuple[Path, Path | None]:
    from workflow import paths as P

    data = state.get("data") or {}
    load_raw = str(data.get("load_csv") or "").strip()
    prices_raw = str(data.get("prices_csv") or "").strip()
    load_path = Path(load_raw) if load_raw else P.WEB_UPLOAD_LOAD_CSV
    prices_path = Path(prices_raw) if prices_raw else (P.WEB_UPLOAD_PRICES_CSV if P.WEB_UPLOAD_PRICES_CSV.is_file() else None)

    if not load_path.is_file() and use_classic_fallback:
        for p in P.IN_FETCH.glob("*.csv"):
            if "price" not in p.name.lower():
                load_path = p
                break
    if prices_path is None or not prices_path.is_file():
        if use_classic_fallback:
            for p in P.IN_FETCH.glob("*.csv"):
                if "price" in p.name.lower():
                    prices_path = p
                    break
    if not load_path.is_file():
        raise FileNotFoundError(
            f"Load CSV missing ({load_path}). Upload in Web UI or place CSV in {P.IN_FETCH}."
        )
    return load_path, prices_path if prices_path and prices_path.is_file() else None


def materialize_from_state(
    state: dict[str, Any],
    *,
    use_classic_fallback: bool = False,
) -> dict[str, str]:
    """Write workflow JSON, scenario template, CSV copies; optional append to company_drop."""
    from workflow import paths as P
    from workflow.user_input import materialize_optional_configs

    sync_from_csv(state, use_classic_fallback=use_classic_fallback)
    P.IN_WEB_USER_INPUT.mkdir(parents=True, exist_ok=True)
    P.USER_INPUT_DIR.mkdir(parents=True, exist_ok=True)

    wf = build_workflow_user_input_json(state)
    P.WORKFLOW_USER_INPUT_JSON.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")

    scen = build_scenario_yaml(state)
    P.USER_SCENARIO_YML.write_text(
        yaml.safe_dump(scen, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )

    load_path, prices_path = resolve_load_and_prices_paths(state, use_classic_fallback=use_classic_fallback)
    P.IN_FETCH.mkdir(parents=True, exist_ok=True)
    fetch_load = P.IN_FETCH / "load_from_web.csv"
    shutil.copy2(load_path, fetch_load)
    fetch_prices = ""
    if prices_path:
        fp = P.IN_FETCH / "prices_from_web.csv"
        shutil.copy2(prices_path, fp)
        fetch_prices = str(fp)

    if bool((state.get("data") or {}).get("append_new_rows_to_company_drop", True)):
        append_src = P.WEB_APPEND_DROP_CSV
        if append_src.is_file():
            P.SUSTAINABLE_UPDATES_DIR.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            dest = P.SUSTAINABLE_UPDATES_DIR / f"web_append_{stamp}.csv"
            shutil.copy2(append_src, dest)

    from workflow.user_input import load_workflow_user_input, materialize_optional_configs

    _po, _c, _e, extras = load_workflow_user_input()
    materialize_optional_configs(extras)

    return {
        "workflow_user_input_json": str(P.WORKFLOW_USER_INPUT_JSON),
        "user_scenario_yaml": str(P.USER_SCENARIO_YML),
        "load_csv": str(load_path),
        "prices_csv": fetch_prices,
        "fetch_load_csv": str(fetch_load),
    }

