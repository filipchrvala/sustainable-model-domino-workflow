"""Streamlit view helpers for tests/dashboard_data.json (unified workflow output)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from .models import METRIC_HELP


def render_kpi_metric(column, label: str, value: str, help_key: str, *, widget_key: str) -> None:
    column.metric(label, value, help=METRIC_HELP.get(help_key))

ROOT = Path(__file__).resolve().parents[2]
UNIFIED = ROOT / "tests" / "dashboard_data.json"
INV_FALLBACK = ROOT / "tests" / "FeasibilityReportPiece_Outputs" / "dashboard_data.json"


def load_unified_payload() -> dict | None:
    for p in (UNIFIED, INV_FALLBACK):
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("format") == "alternate_unified_v1":
                return data
            if "feasibility" in data and "investment" not in data:
                return {"format": "alternate_unified_v1", "investment": data, "timeseries": None}
            return data
    return None


def render_investment(payload: dict) -> None:
    meta = payload.get("meta") or {}
    feas = payload.get("feasibility") or {}
    cfo = feas.get("cfo_notes") or payload.get("cfo_notes") or {}
    grid = payload.get("sizing_grid") or []
    basis = feas.get("model_basis") or meta.get("model_basis") or "parametric_grid_only"

    if meta.get("site_name"):
        st.caption(f"Prevádzka: **{meta['site_name']}**")
    if meta.get("generated_at_utc"):
        st.caption(f"Vygenerované: {meta['generated_at_utc']}")

    if basis == "timeseries_simulation":
        st.success("Hlavné metriky z časovej simulácie (KPI → InvestmentEval).")
    else:
        st.warning(
            "Tento beh používa parametrickú mriežku. Pre časovú simuláciu spusti: "
            "`python run_workflow.py` (bez `--phase investment`)."
        )

    c1, c2, c3, c4 = st.columns(4)
    target_pb = feas.get("target_payback_years")
    achieved = feas.get("achieved_payback_years")
    render_kpi_metric(c1, "Cieľová návratnosť (r.)", f"{target_pb:.1f}" if target_pb is not None else "—", "target_payback", widget_key="dv_tgt")
    render_kpi_metric(c2, "Dosiahnutá návratnosť (r.)", f"{achieved:.2f}" if achieved is not None else "—", "achieved_payback", widget_key="dv_ach")
    render_kpi_metric(c3, "Odporúčaná FVE", f"{feas.get('recommended_kwp', 0):,.0f} kWp", "recommended_kwp", widget_key="dv_kwp")
    render_kpi_metric(c4, "Odporúčaná batéria", f"{feas.get('recommended_kwh', 0):,.0f} kWh", "recommended_kwh", widget_key="dv_kwh")

    if feas.get("feasible"):
        st.success("Cieľová návratnosť je splniteľná.")
    else:
        st.error("Cieľová návratnosť nie je splniteľná pri týchto vstupoch.")

    e1, e2, e3 = st.columns(3)
    render_kpi_metric(e1, "CAPEX (FVE + BESS)", f"{feas.get('capex_eur', 0):,.0f} €", "capex_fve_bess", widget_key="dv_capex")
    render_kpi_metric(e2, "Ročná úspora", f"{feas.get('annual_savings_eur', 0):,.0f} €", "annual_savings_inv", widget_key="dv_sav")
    npv = cfo.get("npv_eur_at_best")
    render_kpi_metric(e3, "NPV", f"{npv:,.0f} €" if npv is not None else "—", "npv_inv", widget_key="dv_npv")

    if grid:
        st.subheader("Mriežka variantov (FVE × batéria)")
        st.dataframe(pd.DataFrame(grid), use_container_width=True, height=360)

    note = cfo.get("scenario_summary")
    if note:
        st.info(note)


def render_unified_dashboard() -> bool:
    raw = load_unified_payload()
    if not raw:
        st.warning("Chýba `tests/dashboard_data.json`. Najprv spusti workflow.")
        return False

    gen = raw.get("generated_at_utc")
    if gen:
        st.caption(f"Posledná aktualizácia (UTC): **{gen}**")

    if raw.get("format") == "alternate_unified_v1":
        inv = raw.get("investment")
        if inv:
            render_investment(inv)
        else:
            st.error("Prázdny investment payload.")
        return True

    if raw.get("format") == "cfo_finance_dashboard_v1":
        k = raw.get("decision_kpis") or {}
        c1, c2, c3, c4 = st.columns(4)
        render_kpi_metric(c1, "Úspora (obdobie)", f"{k.get('operating_savings_period_eur', 0):,.0f} €", "savings_period", widget_key="cfo_sav")
        render_kpi_metric(c2, "CAPEX", f"{k.get('total_capex_eur', 0):,.0f} €", "capex", widget_key="cfo_capex")
        pb = k.get("simple_payback_years")
        render_kpi_metric(c3, "Návratnosť", f"{pb:.2f} r." if pb is not None else "—", "payback", widget_key="cfo_pb")
        render_kpi_metric(c4, "NPV", f"{k.get('npv_operating_eur', 0):,.0f} €", "npv", widget_key="cfo_npv")
        chart = raw.get("single_chart") or {}
        if chart.get("x") and chart.get("series"):
            import plotly.express as px

            st.subheader(chart.get("title", "Graf"))
            df = pd.DataFrame({"datetime": chart["x"]})
            for s in chart["series"]:
                df[s.get("name", "series")] = s.get("values") or []
            ycols = [c for c in df.columns if c != "datetime"]
            if ycols:
                st.plotly_chart(px.line(df, x="datetime", y=ycols), use_container_width=True)
        return True

    st.json(raw)
    return True
