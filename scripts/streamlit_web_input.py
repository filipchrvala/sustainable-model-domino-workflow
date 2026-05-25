"""
Web UI for project settings, consumption/prices CSV, and MRK/PV/battery scenario.

  python -m streamlit run scripts/streamlit_web_input.py

Pri každom poli: ikona ? (nápoveda) — podrobny popis pri prejdeni mysou.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflow import paths as P
from pieces.WebUserInputPiece.models import FIELD_LABELS, H
from pieces.WebUserInputPiece.piece import (
    SYSTEM_SCOPE_OPTIONS,
    annual_load_mwh_from_csv,
    default_state,
    load_state,
    materialize_from_state,
    save_state,
    sync_from_csv,
    sync_scope_from_state,
)
from pieces.DashboardPiece.dashboard_view import render_unified_dashboard
from pieces.WebUserInputPiece.piece import WebUserInputPiece
from pieces.WebUserInputPiece.models import InputModel as WebInput
from workflow.progress_runner import run_full_pipeline_with_progress

STATE_PATH = P.WEB_FORM_STATE_JSON


def _num(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


st.set_page_config(page_title="VRE – web vstup", layout="wide", initial_sidebar_state="expanded")

if "ui_view" not in st.session_state:
    st.session_state.ui_view = "form"
if "form_state" not in st.session_state:
    st.session_state.form_state = load_state(STATE_PATH)

state = st.session_state.form_state
csv_hints = sync_from_csv(state)

if st.session_state.pop("pending_workflow", False):
    save_state(STATE_PATH, state)
    materialize_from_state(state)
    st.header("Spúšťam workflow…")
    progress = st.progress(0.0, text="Pripravujem…")
    step_caption = st.empty()
    try:
        with st.spinner("Počkajte, prebieha výpočet (môže trvať 1–3 minúty)…"):

            def _on_progress(done: int, total: int, label: str) -> None:
                progress.progress(min(1.0, done / max(total, 1)), text=label)
                step_caption.caption(label)

            run_full_pipeline_with_progress(ROOT, input_mode="web", on_progress=_on_progress)
        progress.progress(1.0, text="Workflow dokončený")
        st.session_state.ui_view = "dashboard"
        st.success("Hotovo — zobrazujem dashboard s výsledkami.")
    except Exception as exc:
        st.session_state.ui_view = "form"
        st.error(f"Workflow zlyhal: {exc}")
        st.exception(exc)
    st.rerun()

if st.session_state.ui_view == "dashboard":
    st.title("Výsledky workflow")
    if st.button("← Späť na úpravu vstupov", type="secondary"):
        st.session_state.ui_view = "form"
        st.rerun()
    render_unified_dashboard()
    st.stop()

st.title("Web vstup dát a nastavení")
st.caption(
    "Alternatíva k `UserInputPiece` (CSV). Pri poliach použi **ikonu ?** vpravo od názvu — "
    "zobrazí sa popis pri prejdení mysou."
)

with st.sidebar:
    st.markdown("### Navigácia")
    nav = st.radio(
        "Zobrazenie",
        ["Formulár", "Dashboard výsledkov"],
        index=0 if st.session_state.ui_view == "form" else 1,
        label_visibility="collapsed",
    )
    if nav == "Dashboard výsledkov":
        st.session_state.ui_view = "dashboard"
        st.rerun()
    elif nav == "Formulár" and st.session_state.ui_view == "dashboard":
        st.session_state.ui_view = "form"
        st.rerun()
    st.divider()
    st.markdown("### Nápoveda")
    st.markdown(
        "Každé pole má ikonu **?** — po prejdení myšou uvidíte vysvetlenie vrátane skratiek "
        "(kWp, kWh, RV, NPV…). Kompletný slovník:"
    )
    with st.expander("Slovník všetkých polí (abecedne)", expanded=False):
        for key in sorted(H.keys(), key=lambda k: FIELD_LABELS.get(k, k).lower()):
            title = FIELD_LABELS.get(key, key)
            st.markdown(f"**{title}**")
            st.caption(H[key])
            st.divider()

constraints = state.setdefault("constraints", {})
economics = state.setdefault("economics", {})
scenario = state.setdefault("scenario", {})
mrk = scenario.setdefault("mrk", {})
analysis = scenario.setdefault("analysis", {})
finance = scenario.setdefault("finance", {})
pv_cfg = scenario.setdefault("pv", {})
bat_cfg = scenario.setdefault("battery", {})
equip = scenario.setdefault("equipment", {})
auto = equip.setdefault("auto", {})
bat_piece_cfg = state.setdefault("battery_config", {})
data_cfg = state.setdefault("data", {})
site = constraints.setdefault("site", {})
install = constraints.setdefault("installation", {})
solar_econ = economics.setdefault("solar", {})
batt_econ = economics.setdefault("battery", {})
layout_econ = economics.setdefault("layout", {})

tab_proj, tab_data, tab_scen, tab_save = st.tabs(
    ["Projekt a ekonomika", "Spotreba a ceny", "Scenár MRK / FVE / batéria", "Uložiť a spustiť"]
)

with tab_proj:
    c1, c2 = st.columns(2)
    with c1:
        constraints["site_name"] = st.text_input(
            "Názov prevádzky",
            value=str(constraints.get("site_name", "")),
            help=H["site_name"],
        )
        site["latitude"] = st.number_input(
            "Zem. šírka",
            value=_num(site.get("latitude"), 48.17),
            format="%.4f",
            help=H["site_latitude"],
        )
        site["longitude"] = st.number_input(
            "Zem. dĺžka",
            value=_num(site.get("longitude"), 17.07),
            format="%.4f",
            help=H["site_longitude"],
        )
        constraints["target_payback_years"] = st.number_input(
            "Cieľová návratnosť (r.)",
            value=_num(constraints.get("target_payback_years"), 8.0),
            min_value=1.0,
            help=H["target_payback_years"],
        )
        constraints["max_roof_area_m2"] = st.number_input(
            "Max. plocha strechy (m²)",
            value=_num(constraints.get("max_roof_area_m2"), 8000.0),
            min_value=0.0,
            help=H["max_roof_area_m2"],
        )
        constraints["max_battery_area_m2"] = st.number_input(
            "Max. plocha batérie (m²)",
            value=_num(constraints.get("max_battery_area_m2"), 400.0),
            min_value=0.0,
            help=H["max_battery_area_m2"],
        )
        layout_econ["kwh_per_m2_battery_area"] = st.number_input(
            "Hustota batérie (kWh/m² plochy)",
            value=_num(layout_econ.get("kwh_per_m2_battery_area"), 2.5),
            min_value=0.01,
            step=0.1,
            format="%.2f",
            help=H["kwh_per_m2_battery_area"],
        )
    with c2:
        _scope = sync_scope_from_state(state)
        st.info(
            f"**Rozsah technológií:** {SYSTEM_SCOPE_OPTIONS.get(_scope, _scope)} — "
            "nastavuje sa v záložke **Scenár MRK / FVE / batéria**.",
            icon="ℹ️",
        )
        solar_econ["eur_per_kwp"] = st.number_input(
            "CAPEX FVE (€/kWp)",
            value=_num(solar_econ.get("eur_per_kwp"), 900.0),
            help=H["eur_per_kwp"],
        )
        solar_econ["yield_kwh_per_kwp_year"] = st.number_input(
            "Výnos (kWh/kWp/rok)",
            value=_num(solar_econ.get("yield_kwh_per_kwp_year"), 1000.0),
            help=H["yield_kwh_per_kwp_year"],
        )
        batt_econ["eur_per_kwh"] = st.number_input(
            "CAPEX batérie (€/kWh)",
            value=_num(batt_econ.get("eur_per_kwh"), 350.0),
            help=H["eur_per_kwh"],
        )
        install["mount_type"] = st.selectbox(
            "Montáž",
            ["roof", "ground"],
            index=0 if install.get("mount_type") != "ground" else 1,
            help=H["mount_type"],
        )
        install["shading"] = st.selectbox(
            "Tieň",
            ["none", "low", "medium", "high"],
            index=["none", "low", "medium", "high"].index(str(install.get("shading", "low"))),
            help=H["shading"],
        )

with tab_data:
    st.subheader("Historická spotreba a ceny")
    load_up = st.file_uploader(
        "Spotreba (CSV)",
        type=["csv"],
        key="load_up",
        help=H["load_csv"],
    )
    if load_up is not None:
        P.IN_WEB_USER_INPUT.mkdir(parents=True, exist_ok=True)
        P.WEB_UPLOAD_LOAD_CSV.write_bytes(load_up.getvalue())
        data_cfg["load_csv"] = str(P.WEB_UPLOAD_LOAD_CSV)
        st.success(f"Uložené: {P.WEB_UPLOAD_LOAD_CSV.name}")

    prices_up = st.file_uploader(
        "Ceny (CSV, voliteľné)",
        type=["csv"],
        key="prices_up",
        help=H["prices_csv"],
    )
    if prices_up is not None:
        P.WEB_UPLOAD_PRICES_CSV.write_bytes(prices_up.getvalue())
        data_cfg["prices_csv"] = str(P.WEB_UPLOAD_PRICES_CSV)
        st.success(f"Uložené: {P.WEB_UPLOAD_PRICES_CSV.name}")

    if csv_hints.get("prices_in_load_csv"):
        st.info(
            "Súbor spotreby už obsahuje stĺpec s cenou (€/kWh). **Samostatný CSV cien nemusíte** nahrávať.",
            icon="ℹ️",
        )

    _load_path = Path(str(data_cfg.get("load_csv") or "")) if data_cfg.get("load_csv") else P.WEB_UPLOAD_LOAD_CSV
    if not _load_path.is_file():
        _load_path = P.WEB_UPLOAD_LOAD_CSV

    if _load_path.is_file():
        try:
            preview = pd.read_csv(_load_path, sep=None, engine="python", nrows=500)
            st.dataframe(preview.head(20), use_container_width=True)
            st.caption(f"Riadkov v ukážke: {len(preview)} · súbor: {_load_path.name}")
        except Exception as exc:
            st.warning(f"Náhľad load CSV: {exc}")

        csv_hints = sync_from_csv(state)
        _est = annual_load_mwh_from_csv(_load_path)
        if _est is not None:
            constraints["annual_load_mwh"] = round(_est, 3)
            st.metric(
                "Odhad ročnej spotreby z CSV",
                f"{_est:,.1f} MWh",
                help=H["annual_load_mwh"],
            )
            st.info(
                "Výpočet simulácie, MRK a špičiek ide z **každého 15-min intervalu** v CSV "
                "(stĺpec load_kw). Hodnota vyššie je len súhrn na kontrolu — **nemusíte ju zadávať ručne**.",
                icon="ℹ️",
            )
    else:
        st.warning(
            "Nahrajte CSV so spotrebou — bez neho workflow nevie spustiť presnú simuláciu.",
            icon="⚠️",
        )
        with st.expander("Odhad ročnej spotreby bez CSV (len orientačne)", expanded=False):
            constraints["annual_load_mwh"] = st.number_input(
                "Ročná spotreba (MWh)",
                value=_num(constraints.get("annual_load_mwh"), 1200.0),
                min_value=0.0,
                help=H["annual_load_mwh_manual"],
            )

    st.divider()
    st.subheader("Nové riadky spotreby (voliteľné)")
    data_cfg["append_new_rows_to_company_drop"] = st.checkbox(
        "Poslať nové dáta do company_drop pri uložení",
        value=bool(data_cfg.get("append_new_rows_to_company_drop", True)),
        help=H["append_to_drop"],
    )
    append_up = st.file_uploader(
        "Nová spotreba – CSV na doplnenie",
        type=["csv"],
        key="append_up",
        help=H["append_csv"],
    )
    if append_up is not None:
        P.WEB_APPEND_DROP_CSV.write_bytes(append_up.getvalue())
        st.info(f"Pripravené na ingest: {P.WEB_APPEND_DROP_CSV.name}")

    manual = st.expander("Ručný záznam (jeden interval)")
    with manual:
        m1, m2, m3 = st.columns(3)
        dt = m1.text_input(
            "datetime (ISO)",
            value="2026-01-15 12:00:00",
            help=H["manual_datetime"],
        )
        load_kw = m2.number_input("load_kw", value=100.0, help=H["manual_load_kw"])
        price = m3.number_input(
            "price_eur_per_kwh",
            value=0.12,
            format="%.4f",
            help=H["manual_price"],
        )
        if st.button("Pridať riadok do pending append"):
            row = pd.DataFrame([{"datetime": dt, "load_kw": load_kw, "price_eur_per_kwh": price}])
            P.IN_WEB_USER_INPUT.mkdir(parents=True, exist_ok=True)
            if P.WEB_APPEND_DROP_CSV.is_file():
                old = pd.read_csv(P.WEB_APPEND_DROP_CSV)
                row = pd.concat([old, row], ignore_index=True)
            row.to_csv(P.WEB_APPEND_DROP_CSV, index=False)
            st.success("Riadok pridaný do pending append CSV.")

with tab_scen:
    s1, s2 = st.columns(2)
    with s1:
        if scenario.get("timestep_minutes_from") == "csv":
            st.metric(
                "Krok dát (z CSV)",
                f"{int(scenario.get('timestep_minutes', 15))} min",
                help=H["timestep_minutes"],
            )
            if st.button("Upraviť krok času ručne", key="timestep_manual"):
                scenario["timestep_minutes_from"] = "manual"
                st.rerun()
        else:
            scenario["timestep_minutes"] = int(
                st.number_input(
                    "Krok (min)",
                    value=int(scenario.get("timestep_minutes", 15)),
                    help=H["timestep_minutes"],
                )
            )
            scenario["timestep_minutes_from"] = "manual"

        if csv_hints.get("mrk_peak_kw") is not None:
            st.metric(
                "Najvyššia mes. špička z CSV",
                f"{csv_hints['mrk_peak_kw']:,.1f} kW",
                help=H["mrk_peak_from_csv"],
            )
            if st.button("Použiť ako zmluvný výkon (RV)", key="mrk_use_peak"):
                mrk["contract_kw"] = float(csv_hints["mrk_peak_kw"])
                mrk["contract_kw_from"] = "csv"
                st.rerun()
        mrk["contract_kw"] = st.number_input(
            "MRK zmluvný výkon (kW)",
            value=_num(mrk.get("contract_kw"), _num(mrk.get("suggested_contract_kw"), 420.0)),
            help=H["contract_kw"],
        )
        mrk["fee_eur_per_kw_month"] = st.number_input(
            "Poplatok MRK (€/kW/mes)",
            value=_num(mrk.get("fee_eur_per_kw_month"), 4.85),
            help=H["fee_eur_per_kw_month"],
        )
        mrk["excess_peak_penalty_eur_per_kw"] = st.number_input(
            "Penalizácia nad RV (€/kW)",
            value=_num(mrk.get("excess_peak_penalty_eur_per_kw"), 32.0),
            help=H["excess_peak_penalty_eur_per_kw"],
        )
        equip["selection_mode"] = st.selectbox(
            "Režim návrhu",
            ["auto", "manual"],
            index=0 if equip.get("selection_mode") != "manual" else 1,
            help=H["selection_mode"],
        )
        _scope_keys = list(SYSTEM_SCOPE_OPTIONS.keys())
        _cur = str(equip.get("system_scope") or "pv_and_battery").lower()
        if _cur not in SYSTEM_SCOPE_OPTIONS:
            _cur = "pv_and_battery"
        equip["system_scope"] = st.selectbox(
            "Rozsah technológií (čo simulovať)",
            options=_scope_keys,
            index=_scope_keys.index(_cur),
            format_func=lambda k: SYSTEM_SCOPE_OPTIONS[k],
            help=H["system_scope"],
        )
        sync_scope_from_state(state)
        scope = str(equip["system_scope"])
        show_pv = scope in ("pv_and_battery", "pv_only")
        show_bat = scope in ("pv_and_battery", "battery_only")

        if equip["selection_mode"] == "manual":
            st.markdown("**Manuálne kapacity**")
            m1, m2 = st.columns(2)
            if show_pv:
                pv_cfg["installed_kwp"] = m1.number_input(
                    "FVE – inštalovaný výkon (kWp)",
                    value=_num(pv_cfg.get("installed_kwp"), 400.0),
                    min_value=0.0,
                    step=10.0,
                    help=H["installed_kwp"],
                )
                m1.caption(
                    f"Výnos a CAPEX FVE sa berú z **Projekt a ekonomika** "
                    f"({_num(solar_econ.get('yield_kwh_per_kwp_year'), 1000):.0f} kWh/kWp/rok, "
                    f"{_num(solar_econ.get('eur_per_kwp'), 900):.0f} €/kWp)."
                )
            else:
                pv_cfg["installed_kwp"] = 0.0
            if show_bat:
                bat_cfg["energy_kwh"] = m2.number_input(
                    "Batéria – kapacita (kWh)",
                    value=_num(bat_cfg.get("energy_kwh", bat_cfg.get("capacity_kWh")), 200.0),
                    min_value=0.0,
                    step=5.0,
                    help=H["energy_kwh"],
                )
                bat_cfg["max_c_rate"] = m2.number_input(
                    "Max. C-rate batérie",
                    value=_num(bat_cfg.get("max_c_rate", bat_piece_cfg.get("max_c_rate")), 0.5),
                    min_value=0.05,
                    max_value=2.0,
                    format="%.2f",
                    help=H["max_c_rate"],
                )
                bat_piece_cfg["max_c_rate"] = bat_cfg["max_c_rate"]
            else:
                bat_cfg["energy_kwh"] = 0.0
        else:
            st.markdown("**Auto optimalizácia**")
            gs = auto.setdefault("grid_sweep", {})
            with st.expander("Mriežka variantov (FVE × batéria) – rozsahy pre tabuľku v dashboarde", expanded=True):
                b = csv_hints.get("bounds") or {}
                if b:
                    st.caption(
                        f"Max. z CSV a plôch (odhad): FVE **{b.get('max_kwp', 0):.0f} kWp**, "
                        f"batéria **{b.get('max_kwh', 0):.0f} kWh** — horné hranice mriežky sa doplnia automaticky."
                    )
                    if st.button("Obnoviť max. mriežky z CSV a plôch", key="grid_bounds_refresh"):
                        gs["kwp_max"] = round(float(b["max_kwp"]), 0)
                        gs["kwh_max"] = round(float(b["max_kwh"]), 0)
                        gs["grid_bounds_from"] = "csv"
                        st.rerun()
                st.caption(
                    "Tu nastavíš **obidva rozmery** mriežky. Ak je len jedna hodnota kWh, zväčši "
                    "`kwh_max` alebo vypni „Len fyzické limity“ (inak platí max. z plochy batérie)."
                )
                g1, g2, g3 = st.columns(3)
                gs["kwp_min"] = g1.number_input(
                    "FVE min (kWp)",
                    value=_num(gs.get("kwp_min"), 100.0),
                    min_value=0.0,
                    help=H["grid_kwp_min"],
                )
                gs["kwp_max"] = g1.number_input(
                    "FVE max (kWp)",
                    value=_num(gs.get("kwp_max"), 500.0),
                    min_value=0.0,
                    help=H["grid_kwp_max"],
                )
                gs["kwp_step"] = g1.number_input(
                    "FVE krok (kWp)",
                    value=_num(gs.get("kwp_step"), 50.0),
                    min_value=1.0,
                    help=H["grid_kwp_step"],
                )
                gs["kwh_min"] = g2.number_input(
                    "Batéria min (kWh)",
                    value=_num(gs.get("kwh_min"), 50.0),
                    min_value=0.0,
                    help=H["grid_kwh_min"],
                )
                gs["kwh_max"] = g2.number_input(
                    "Batéria max (kWh)",
                    value=_num(gs.get("kwh_max"), 300.0),
                    min_value=0.0,
                    help=H["grid_kwh_max"],
                )
                gs["kwh_step"] = g2.number_input(
                    "Batéria krok (kWh)",
                    value=_num(gs.get("kwh_step"), 50.0),
                    min_value=1.0,
                    help=H["grid_kwh_step"],
                )
                gs["respect_physical_bounds"] = g3.checkbox(
                    "Len fyzické limity (plocha/CAPEX)",
                    value=bool(gs.get("respect_physical_bounds", False)),
                    help=H["grid_respect_physical"],
                )
                if st.checkbox(
                    "Mriežku upravujem ručne (nezmeniť max. z CSV)",
                    value=gs.get("grid_bounds_from") == "manual",
                    key="grid_manual",
                ):
                    gs["grid_bounds_from"] = "manual"
                nk = max(1, int((gs["kwp_max"] - gs["kwp_min"]) / max(gs["kwp_step"], 1)) + 1)
                nw = max(1, int((gs["kwh_max"] - gs["kwh_min"]) / max(gs["kwh_step"], 1)) + 1)
                g3.info(f"Odhad variantov: **{nk} × {nw} = {nk * nw}**")
            a1, a2 = st.columns(2)
            auto["objective"] = a1.selectbox(
                "Cieľ",
                ["max_npv", "shortest_payback"],
                index=0 if str(auto.get("objective", "max_npv")) != "shortest_payback" else 1,
                help=H["auto_objective"],
            )
            auto["max_configurations"] = int(
                a1.number_input(
                    "Max. kombinácií",
                    value=int(auto.get("max_configurations", 180)),
                    min_value=10,
                    max_value=500,
                    help=H["max_configurations"],
                )
            )
            with st.expander("Kroky auto optimalizácie (ak nemáte vlastnú mriežku vyššie)", expanded=False):
                auto["kwp_step"] = st.number_input(
                    "Krok kWp (záložný)",
                    value=_num(auto.get("kwp_step"), _num(gs.get("kwp_step"), 50.0)),
                    min_value=1.0,
                    help=H["kwp_step"],
                )
                auto["kwh_step"] = st.number_input(
                    "Krok kWh (záložný)",
                    value=_num(auto.get("kwh_step"), _num(gs.get("kwh_step"), 25.0)),
                    min_value=1.0,
                    help=H["kwh_step"],
                )
            if show_pv:
                auto["min_pv_kwp"] = a1.number_input(
                    "Min. PV (kWp)",
                    value=_num(auto.get("min_pv_kwp"), 100.0),
                    min_value=0.0,
                    help=H["min_pv_kwp"],
                )
            if show_bat:
                auto["min_battery_kwh"] = a2.number_input(
                    "Min. batéria (kWh)",
                    value=_num(auto.get("min_battery_kwh"), 100.0),
                    min_value=0.0,
                    help=H["min_battery_kwh"],
                )
    with s2:
        analysis["discount_rate"] = st.number_input(
            "Diskontná sadzba",
            value=_num(analysis.get("discount_rate"), 0.08),
            format="%.3f",
            help=H["discount_rate"],
        )
        analysis["amortization_years"] = int(
            st.number_input(
                "Amortizácia (r.)",
                value=int(analysis.get("amortization_years", 15)),
                min_value=1,
                help=H["amortization_years"],
            )
        )
        finance["enabled"] = st.checkbox(
            "Finance layer",
            value=bool(finance.get("enabled", True)),
            help=H["finance_enabled"],
        )
        finance["debt_ratio_of_capex"] = st.number_input(
            "Podiel dlhu z CAPEX",
            value=_num(finance.get("debt_ratio_of_capex"), 0.6),
            format="%.2f",
            help=H["debt_ratio_of_capex"],
        )
        analysis["enable_trading_only_scenario"] = st.checkbox(
            "Trading-only scenár",
            value=bool(analysis.get("enable_trading_only_scenario", True)),
            help=H["trading_only"],
        )
        analysis["enable_c_rate_sweep"] = st.checkbox(
            "C-rate sweep",
            value=bool(analysis.get("enable_c_rate_sweep", True)),
            help=H["c_rate_sweep"],
        )

with tab_save:
    st.subheader("Uložiť a validovať")
    if STATE_PATH.is_file():
        meta = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        st.caption(f"Posledné uloženie (UTC): {meta.get('saved_at_utc', '—')}")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button(
            "Uložiť formulár",
            type="primary",
            use_container_width=True,
            help=H["btn_save"],
        ):
            save_state(STATE_PATH, state)
            st.session_state.form_state = state
            st.success(f"Uložené: {STATE_PATH.relative_to(ROOT)}")

    with col_b:
        if st.button(
            "Uložiť + validovať (piece)",
            use_container_width=True,
            help=H["btn_validate"],
        ):
            save_state(STATE_PATH, state)
            paths = materialize_from_state(state)
            piece = WebUserInputPiece.__new__(WebUserInputPiece)
            piece.results_path = str(P.OUT_USER_INPUT)
            out = piece.piece_function(
                WebInput(
                    web_form_state_json=str(STATE_PATH),
                    scenario_yaml=str(P.GENERATED_SCENARIO_YML),
                )
            )
            st.success(out.message)
            st.json(out.model_dump())

    with col_c:
        if st.button(
            "Spustiť celý workflow (web)",
            use_container_width=True,
            help=H["btn_run_workflow"],
        ):
            save_state(STATE_PATH, state)
            st.session_state.form_state = state
            st.session_state.pending_workflow = True
            st.rerun()

    st.divider()
    st.markdown("**Klasický CSV režim:**")
    st.code("python run_workflow.py --input-mode csv", language="bash")
