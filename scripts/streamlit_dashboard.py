"""
Combined Streamlit app: investment proposal + original time-series section (DashboardPiece graphs).

  python -m streamlit run scripts/streamlit_dashboard.py

Reads: tests/dashboard_data.json (alternate_unified_v1), optionally fallback timeseries JSON.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pieces.DashboardPiece.piece import load_unified_payload, render_investment, render_unified_dashboard
from pieces.DashboardPiece.models import METRIC_HELP
from pieces.DashboardPiece.piece import render_kpi_metric

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
UNIFIED = ROOT / "tests" / "dashboard_data.json"
INV_FALLBACK = ROOT / "tests" / "FeasibilityReportPiece_Outputs" / "dashboard_data.json"
TS_FALLBACK = ROOT / "tests" / "DashboardPiece_Outputs" / "dashboard_data.json"
ALERTS_CSV = ROOT / "tests" / "AnomalyAlertPiece_Outputs" / "anomaly_alerts.csv"
COMPANY_DROP = ROOT / "tests" / "sustainable" / "company_drop"


def _file_mtime_label(path: Path) -> str:
    if not path.is_file():
        return "—"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def _maybe_auto_rerun(interval_sec: int) -> None:
    if interval_sec <= 0:
        return
    key = "_dashboard_auto_refresh_ts"
    now = time.time()
    if key not in st.session_state:
        st.session_state[key] = now
        return
    if now - float(st.session_state[key]) >= interval_sec:
        st.session_state[key] = now
        st.rerun()


def _render_live_sidebar() -> int:
    st.sidebar.header("Live data")
    auto = st.sidebar.checkbox("Auto-refresh obrazovky", value=True)
    interval = int(
        st.sidebar.selectbox("Interval obnovy UI (s)", options=[15, 30, 60, 120, 300], index=2)
    )
    if st.sidebar.button("Obnovit data + alerty", type="primary", use_container_width=True):
        with st.spinner("Ingest, forecast, alerty, dashboard JSON…"):
            from workflow.live_refresh import run_operational_refresh

            run_operational_refresh(refresh_dashboard=True, include_timeseries=True)
        st.rerun()
    st.sidebar.caption(f"`dashboard_data.json`: {_file_mtime_label(UNIFIED)}")
    st.sidebar.caption(f"`anomaly_alerts.csv`: {_file_mtime_label(ALERTS_CSV)}")
    drop_n = len([p for p in COMPANY_DROP.glob("*") if p.is_file()]) if COMPANY_DROP.is_dir() else 0
    st.sidebar.caption(f"Súbory v `company_drop`: {drop_n}")
    st.sidebar.markdown(
        "Na pozadí môže bežať watcher:\n\n"
        "`python scripts/dashboard_live.py --watch`\n\n"
        "alebo `run_live_dashboard.ps1` (Streamlit + watcher)."
    )
    return interval if auto else 0


def _load_payload() -> dict | None:
    for p in (UNIFIED, INV_FALLBACK):
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("format") == "alternate_unified_v1":
                return data
            if "feasibility" in data and "investment" not in data:
                return {"investment": data, "timeseries": None}
            return data
    fb = ROOT / "tests" / "FeasibilityReportPiece_Outputs" / "feasibility_report.json"
    if fb.is_file():
        return {
            "investment": {
                "feasibility": json.loads(fb.read_text(encoding="utf-8")),
                "meta": {},
                "sizing_grid": [],
            },
            "timeseries": None,
        }
    return None


def _get_timeseries_payload(raw: dict, *, allow_fallback: bool) -> dict | None:
    """Time-series branch from unified payload; fallback only when explicitly allowed."""
    ts = raw.get("timeseries")
    if isinstance(ts, dict) and (
        ts.get("datasets") is not None
        or ts.get("meta")
        or ts.get("alerts_and_drift") is not None
        or ts.get("single_chart") is not None
        or ts.get("decision_kpis") is not None
    ):
        return ts
    if allow_fallback and TS_FALLBACK.is_file():
        return json.loads(TS_FALLBACK.read_text(encoding="utf-8"))
    return None


# use render_unified_dashboard / piece._render_investment

def _render_investment_legacy(payload: dict) -> None:
    meta = payload.get("meta") or {}
    feas = payload.get("feasibility") or {}
    cfo = feas.get("cfo_notes") or payload.get("cfo_notes") or {}
    grid = payload.get("sizing_grid") or []

    basis = feas.get("model_basis") or meta.get("model_basis") or "parametric_grid_only"

    if meta.get("site_name"):
        st.caption(f"Site / name: **{meta['site_name']}**")
    if meta.get("generated_at_utc"):
        st.caption(f"Generated: {meta['generated_at_utc']}")

    if basis == "timeseries_simulation":
        st.success(
            "**Primary metrics** come from the **time-series simulation** (KPI → InvestmentEval). "
            "The parametric grid below is a preliminary estimate."
        )
    else:
        st.warning(
            "**This run** uses only the **parametric model** (grid). "
            "Run `python run_workflow.py` without `--phase investment` for savings from 15-minute data."
        )

    feasible = feas.get("feasible", False)
    target_pb = feas.get("target_payback_years")
    achieved = feas.get("achieved_payback_years")
    min_pb = feas.get("minimum_payback_in_search_space_years")

    st.subheader("Decision summary")
    c1, c2, c3, c4 = st.columns(4)
    render_kpi_metric(c1, "Cieľová návratnosť (r.)", f"{target_pb:.1f}" if target_pb is not None else "—", "target_payback", widget_key="app_tgt_pb")
    render_kpi_metric(c2, "Dosiahnutá návratnosť (r.)", f"{achieved:.2f}" if achieved is not None else "—", "achieved_payback", widget_key="app_ach_pb")
    render_kpi_metric(c3, "Odporúčaná FVE", f"{feas.get('recommended_kwp', 0):,.0f} kWp", "recommended_kwp", widget_key="app_kwp")
    render_kpi_metric(c4, "Odporúčaná batéria", f"{feas.get('recommended_kwh', 0):,.0f} kWh", "recommended_kwh", widget_key="app_kwh")

    if feasible:
        st.success("The target payback is **achievable** within this model.")
    else:
        st.error("With the given inputs the target is **not achievable**.")
        if min_pb is not None:
            st.info(f"**Minimum** achievable payback (in the grid): **{min_pb:.2f} y.**")

    st.subheader("Economics (main output)")
    e1, e2, e3 = st.columns(3)
    render_kpi_metric(e1, "CAPEX (FVE + BESS)", f"{feas.get('capex_eur', 0):,.0f} €", "capex_fve_bess", widget_key="app_capex")
    lbl_sav = "Ročná úspora (simulácia)" if basis == "timeseries_simulation" else "Ročná úspora (mriežka)"
    render_kpi_metric(e2, lbl_sav, f"{feas.get('annual_savings_eur', 0):,.0f} €", "annual_savings_inv", widget_key="app_sav")
    npv = cfo.get("npv_eur_at_best")
    lbl_npv = "NPV (diskontované)" if basis == "timeseries_simulation" else "NPV (mriežka)"
    render_kpi_metric(e3, lbl_npv, f"{npv:,.0f} €" if npv is not None else "—", "npv_inv", widget_key="app_npv")

    pe = feas.get("parametric_estimate") or {}
    if pe and basis == "timeseries_simulation":
        with st.expander("Comparison: parametric estimate before simulation", expanded=False):
            st.caption(pe.get("label", ""))
            p1, p2, p3 = st.columns(3)
            render_kpi_metric(
                p1,
                "Návratnosť (mriežka)",
                f"{pe.get('payback_years', 0):.2f}" if pe.get("payback_years") is not None else "—",
                "payback_grid",
                widget_key="app_pe_pb",
            )
            render_kpi_metric(p2, "Úspora (mriežka)", f"{pe.get('annual_savings_eur', 0):,.0f} €", "savings_grid", widget_key="app_pe_sav")
            render_kpi_metric(p3, "NPV (mriežka)", f"{pe.get('npv_eur', 0):,.0f} €", "npv_grid", widget_key="app_pe_npv")

    sim = feas.get("simulation")
    if sim and basis == "timeseries_simulation":
        with st.expander("Simulation detail (InvestmentEval)", expanded=False):
            s1, s2 = st.columns(2)
            s1.write(
                f"- Solar LCOE (indicative): **{sim.get('solar_lcoe_eur_per_mwh', '—')}** €/MWh\n"
                f"- CO₂ (grid savings): **{sim.get('annual_co2_saved_ton', '—')}** t/year\n"
            )
            cycles = sim.get("battery_cycles_est")
            s2.write(f"- **Estimated battery cycles** (annual equiv.): {cycles if cycles is not None else '—'}")

    sens = cfo.get("sensitivity_matrix") or []
    if sens:
        st.subheader("Sensitivity (±10% on savings and CAPEX)")
        st.caption(cfo.get("sensitivity_hint", ""))
        st.dataframe(pd.DataFrame(sens), use_container_width=True, height=280)

    hw = feas.get("hardware") or {}
    pv_hw = hw.get("pv") or cfo.get("recommended_pv_hardware") or {}
    bat_hw = hw.get("battery") or cfo.get("recommended_battery_hardware") or {}

    st.subheader("Specific hardware (catalog)")
    h1, h2 = st.columns(2)
    with h1:
        st.markdown("**Solar PV (modules)**")
        if pv_hw.get("catalog_module_count"):
            st.caption(
                f"Catalog for selection: **{pv_hw['catalog_module_count']:,}** modules — {pv_hw.get('catalog_source', '')}"
            )
        if pv_hw:
            st.write(
                f"- **{pv_hw.get('module_manufacturer', '—')}** — {pv_hw.get('module_model', '—')}\n"
                f"- Module power: **{pv_hw.get('module_power_wp', '—')} Wp**\n"
                f"- Module count (estimate): **{pv_hw.get('module_count', '—')}** pcs → "
                f"~**{pv_hw.get('installed_kwp_dc_approx', '—')} kWp** DC\n"
                f"- SAM key (pvlib): `{pv_hw.get('sam_key', '—')}`"
            )
            if pv_hw.get("panel_selection_rationale"):
                st.markdown("**Why this module type (auto)**")
                for line in pv_hw["panel_selection_rationale"]:
                    st.markdown(f"- {line}")
            pr = pv_hw.get("panel_ranking") or []
            if pr:
                st.markdown("**Alternative ranking in catalog (score)**")
                st.dataframe(pd.DataFrame(pr), use_container_width=True, height=280)
            if pv_hw.get("sam_verify_warning"):
                st.warning(pv_hw["sam_verify_warning"])
            if pv_hw.get("sam_verify_note"):
                st.info(pv_hw["sam_verify_note"])
        else:
            st.info("No module data available.")
    with h2:
        st.markdown("**Battery (ESS)**")
        if bat_hw and bat_hw.get("nominal_kwh_installed", 0):
            st.write(
                f"- **{bat_hw.get('manufacturer', '—')}** — {bat_hw.get('product_line', '—')}\n"
                f"- Units: **{bat_hw.get('units', 1)}** × "
                f"**{bat_hw.get('nominal_kwh_per_unit', '—')} kWh** → "
                f"**{bat_hw.get('nominal_kwh_installed', '—')} kWh**"
            )
        else:
            st.info("Zero or unknown battery capacity.")

    if cfo.get("scenario_summary"):
        st.markdown("**Narrative summary**")
        st.write(cfo["scenario_summary"])
    for a in cfo.get("assumptions") or []:
        st.caption(f"• {a}")

    if grid:
        st.subheader("Variant grid (kWp × kWh)")
        df = pd.DataFrame(grid)
        st.dataframe(df, use_container_width=True, height=400)
        if len(df) > 1 and "kwp" in df.columns and "kwh" in df.columns and "payback_years" in df.columns:
            dfp = df.dropna(subset=["payback_years"])
            if not dfp.empty:
                kw = dict(
                    x="kwp",
                    y="kwh",
                    color="payback_years",
                    color_continuous_scale="RdYlGn_r",
                    title="Payback (y.) by PV and battery size",
                )
                if "capex_eur" in dfp.columns:
                    kw["size"] = "capex_eur"
                    kw["size_max"] = 60
                st.plotly_chart(px.scatter(dfp, **kw), use_container_width=True)


st.set_page_config(page_title="Alternate – VRE dashboard", layout="wide")
st.title("Alternate – integrated dashboard")
st.caption("Pod každou metrikou je tlačidlo **?** — kliknutím zobrazíte slovenské vysvetlenie (NPV, CAPEX, kWp…).")

_refresh_sec = _render_live_sidebar()
_maybe_auto_rerun(_refresh_sec)

if not render_unified_dashboard():
    st.stop()

st.divider()
st.caption(f"Data: `{UNIFIED.relative_to(ROOT)}` · refresh: `python run_workflow.py`")
