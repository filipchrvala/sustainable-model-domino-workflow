"""Hustý CFO dashboard – jedna obrazovka, profesionálny vzhľad."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from .piece import _grid_to_frame, get_timeseries_payload

C_NAVY = "#133667"
C_BLUE = "#2D71C4"
C_TEAL = "#219AAC"
C_GREEN = "#31855A"
C_GRAY = "#6C7581"
C_RED = "#BF414E"
C_CARD = "#ffffff"
C_BORDER = "#dde3eb"


def _fmt(value: float | None, suffix: str = " EUR") -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    return f"{float(value):,.0f}{suffix}".replace(",", " ")


def _annualize(period_cost: float, period_savings: float, annual_savings: float) -> float:
    if period_savings and abs(period_savings) > 1e-9:
        return period_cost * (annual_savings / period_savings)
    return period_cost


def _extract_context(raw: dict) -> dict:
    inv = raw.get("investment") or {}
    feas = inv.get("feasibility") or {}
    cfo = feas.get("cfo_notes") or {}
    sim = feas.get("simulation") or {}
    ts = get_timeseries_payload(raw, allow_fallback=True) or {}
    kpi = ts.get("decision_kpis") or {}
    alerts = (ts.get("alerts_and_drift") or {}).get("summary") or {}

    savings = float(feas.get("annual_savings_eur") or kpi.get("operating_savings_annual_estimate_eur") or 0)
    period_sav = float(kpi.get("operating_savings_period_eur") or 1)
    pb = feas.get("achieved_payback_years") or kpi.get("simple_payback_years")
    npv = sim.get("npv_eur") or cfo.get("npv_eur_at_best") or kpi.get("npv_operating_eur")
    capex = float(feas.get("capex_eur") or kpi.get("total_capex_eur") or 0)

    annual_base = annual_opt = None
    if kpi.get("operating_cost_baseline_eur") is not None:
        annual_base = _annualize(float(kpi["operating_cost_baseline_eur"]), period_sav, savings)
        annual_opt = _annualize(float(kpi["operating_cost_with_pv_battery_eur"]), period_sav, savings)

    grid_df = _grid_to_frame(inv.get("sizing_grid") or [])
    min_pb = feas.get("minimum_payback_in_search_space_years")
    if grid_df is not None and not grid_df.empty and "payback_years" in grid_df.columns:
        min_pb = float(grid_df["payback_years"].min())

    return {
        "feas": feas,
        "cfo": cfo,
        "sim": sim,
        "kpi": kpi,
        "alerts": alerts,
        "kwp": float(feas.get("recommended_kwp") or 0),
        "kwh": float(feas.get("recommended_kwh") or 0),
        "savings": savings,
        "payback": float(pb) if pb is not None else None,
        "npv": float(npv) if npv is not None else None,
        "capex": capex,
        "solar_capex": float(sim.get("solar_capex_eur") or 0),
        "bess_capex": float(sim.get("battery_capex_eur") or 0),
        "annual_base": annual_base,
        "annual_opt": annual_opt,
        "rv": kpi.get("rv_downsizing_potential_kw"),
        "min_pb": min_pb,
        "grid_df": grid_df,
        "sensitivity": cfo.get("sensitivity_matrix") or [],
        "basis": feas.get("model_basis") or "timeseries_simulation",
        "grid_n": len(grid_df) if grid_df is not None else 0,
    }


def _kpi_tile(label: str, value: str, accent: str) -> str:
    return f"""
    <div class="cfo-tile" style="border-left:5px solid {accent};">
        <div class="cfo-tile-label">{label}</div>
        <div class="cfo-tile-value">{value}</div>
    </div>"""


def _html_table(df: pd.DataFrame, col_a: str, col_b: str) -> str:
    body = "".join(
        f"<tr><td>{row[col_a]}</td><td class='val'>{row[col_b]}</td></tr>"
        for _, row in df.iterrows()
    )
    return (
        f"<table class='cfo-table'><thead><tr>"
        f"<th>{col_a}</th><th style='text-align:right'>{col_b}</th>"
        f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _html_table_wide(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    head_parts = []
    for i, c in enumerate(cols):
        if i > 0:
            head_parts.append(f"<th style='text-align:right'>{c}</th>")
        else:
            head_parts.append(f"<th>{c}</th>")
    head = "".join(head_parts)
    body_rows = []
    for _, row in df.iterrows():
        cells = []
        for i, c in enumerate(cols):
            val = row[c]
            if i > 0:
                cells.append(f"<td class='val'>{val}</td>")
            else:
                cells.append(f"<td>{val}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    body = "".join(body_rows)
    return f"<table class='cfo-table'><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_presentation_dashboard(raw: dict) -> None:
    ctx = _extract_context(raw)
    cost_drop_pct = None
    if ctx["annual_base"] and ctx["annual_opt"] and ctx["annual_base"] > 0:
        cost_drop_pct = (ctx["annual_base"] - ctx["annual_opt"]) / ctx["annual_base"] * 100

    st.markdown(
        """
        <div class="cfo-header">
            <div class="cfo-header-title">Investičný energetický prehľad</div>
            <div class="cfo-header-sub">SPICE UC3 · auto návrh FVE a batérie · dáta ABCD (4 oddelenia) · časová simulácia</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- KPI pásmo (8 metrík) ---
    tiles = [
        ("Ročná úspora", _fmt(ctx["savings"], " EUR/rok"), C_BLUE),
        ("Návratnosť", f"{ctx['payback']:.1f} r." if ctx["payback"] else "—", C_TEAL),
        ("NPV (prevádzka)", _fmt(ctx["npv"]), C_NAVY if (ctx["npv"] or 0) >= 0 else C_RED),
        ("CAPEX celkom", _fmt(ctx["capex"]), C_GRAY),
        ("Náklady / rok", f"{_fmt(ctx['annual_base'])} → {_fmt(ctx['annual_opt'])}", C_BLUE),
        ("Pokles nákladov", f"{cost_drop_pct:.1f} %" if cost_drop_pct else "—", C_GREEN),
        ("FVE / batéria", f"{ctx['kwp']:.0f} kWp / {ctx['kwh']:.0f} kWh", C_NAVY),
        ("RV potenciál", f"{float(ctx['rv']):.0f} kW" if ctx["rv"] else "—", C_GREEN),
    ]
    for batch in (tiles[:4], tiles[4:]):
        st.markdown(
            '<div class="cfo-tile-row">' + "".join(_kpi_tile(l, v, a) for l, v, a in batch) + "</div>",
            unsafe_allow_html=True,
        )

    col_l, col_r = st.columns([1.15, 1])

    with col_l:
        st.markdown('<div class="cfo-section">Ročné prevádzkové náklady a úspora</div>', unsafe_allow_html=True)
        if ctx["annual_base"] and ctx["annual_opt"]:
            fig = go.Figure()
            fig.add_trace(
                go.Bar(
                    name="Baseline",
                    x=["Baseline", "FVE + batéria"],
                    y=[ctx["annual_base"], ctx["annual_opt"]],
                    marker_color=[C_GRAY, C_BLUE],
                    text=[_fmt(ctx["annual_base"]), _fmt(ctx["annual_opt"])],
                    textposition="outside",
                )
            )
            fig.add_hline(y=ctx["annual_base"], line_dash="dot", line_color="#94a3b8", opacity=0.9)
            _axis_color = "#0f172a"
            fig.update_layout(
                template="plotly_white",
                height=280,
                margin=dict(l=56, r=20, t=16, b=56),
                paper_bgcolor="#ffffff",
                plot_bgcolor="#ffffff",
                showlegend=False,
                font=dict(size=14, color=_axis_color),
                xaxis=dict(
                    tickfont=dict(size=15, color=_axis_color),
                    title_font=dict(size=14, color=_axis_color),
                    linecolor="#cbd5e1",
                    gridcolor="#eef2f6",
                ),
                yaxis=dict(
                    title="EUR / rok",
                    tickfont=dict(size=14, color=_axis_color),
                    title_font=dict(size=15, color=_axis_color),
                    tickformat=",.0f",
                    linecolor="#cbd5e1",
                    gridcolor="#e2e8f0",
                    zerolinecolor="#e2e8f0",
                ),
            )
            fig.update_traces(
                textfont=dict(size=15, color=_axis_color),
                cliponaxis=False,
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        st.markdown('<div class="cfo-section">Citlivosť investície (±10 %)</div>', unsafe_allow_html=True)
        if ctx["sensitivity"]:
            sens = pd.DataFrame(ctx["sensitivity"])
            sens = sens.rename(
                columns={
                    "scenario": "Scenár",
                    "payback_years": "Návratnosť (r.)",
                    "npv_eur": "NPV (EUR)",
                    "capex_eur": "CAPEX (EUR)",
                    "annual_savings_eur": "Ročná úspora (EUR)",
                }
            )
            for c in ("Návratnosť (r.)", "NPV (EUR)", "CAPEX (EUR)", "Ročná úspora (EUR)"):
                if c in sens.columns:
                    if c == "Návratnosť (r.)":
                        sens[c] = sens[c].apply(lambda x: f"{float(x):.2f}" if pd.notna(x) else "—")
                    else:
                        sens[c] = sens[c].apply(lambda x: f"{float(x):,.0f}".replace(",", " ") if pd.notna(x) else "—")
            st.markdown(_html_table_wide(sens), unsafe_allow_html=True)

    with col_r:
        st.markdown('<div class="cfo-section">Odporúčaná investícia</div>', unsafe_allow_html=True)
        inv_rows = pd.DataFrame(
            [
                ("Konfigurácia FVE", f"{ctx['kwp']:.0f} kWp"),
                ("Kapacita BESS", f"{ctx['kwh']:.0f} kWh"),
                ("CAPEX FVE", _fmt(ctx["solar_capex"])),
                ("CAPEX batéria", _fmt(ctx["bess_capex"])),
                ("CAPEX celkom", _fmt(ctx["capex"])),
                ("Ročná prevádzková úspora", _fmt(ctx["savings"], " EUR")),
                ("Jednoduchá návratnosť", f"{ctx['payback']:.2f} r." if ctx["payback"] else "—"),
                ("NPV (diskontované)", _fmt(ctx["npv"])),
                ("Min. návratnosť v mriežke", f"{ctx['min_pb']:.2f} r." if ctx["min_pb"] else "—"),
                ("Počet vyhodnotených variantov", str(ctx["grid_n"])),
            ],
            columns=["Ukazovateľ", "Hodnota"],
        )
        st.markdown(_html_table(inv_rows, "Ukazovateľ", "Hodnota"), unsafe_allow_html=True)

        st.markdown('<div class="cfo-section">Prevádzkový monitoring (súhrn)</div>', unsafe_allow_html=True)
        al = ctx["alerts"]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Alerty celkom", int(al.get("total", 0)))
        m2.metric("Kritické", int(al.get("critical", 0)))
        m3.metric("Výstrahy", int(al.get("warning", 0)))
        m4.metric("Info", int(al.get("info", 0)))

    st.markdown('<div class="cfo-section">Mriežka variantov – návratnosť (výber)</div>', unsafe_allow_html=True)
    gdf = ctx["grid_df"]
    if gdf is not None and not gdf.empty:
        c_hm, c_tbl = st.columns([1.1, 1])
        with c_hm:
            if gdf["fve_kwp"].nunique() > 1 and gdf["bateria_kwh"].nunique() > 1:
                pivot = gdf.pivot_table(
                    index="bateria_kwh", columns="fve_kwp", values="payback_years", aggfunc="mean"
                )
                fig_hm = px.imshow(
                    pivot,
                    labels=dict(x="FVE (kWp)", y="Batéria (kWh)", color="r."),
                    color_continuous_scale="RdYlGn_r",
                    aspect="auto",
                    text_auto=".1f",
                )
                _axis_color = "#0f172a"
                fig_hm.update_layout(
                    template="plotly_white",
                    height=300,
                    margin=dict(l=56, r=12, t=44, b=48),
                    title=dict(text=f"Odporúčanie: {ctx['kwp']:.0f}/{ctx['kwh']:.0f} kWh", font=dict(size=15, color=_axis_color)),
                    font=dict(size=13, color=_axis_color),
                    paper_bgcolor="#ffffff",
                    plot_bgcolor="#ffffff",
                    xaxis=dict(tickfont=dict(size=12, color=_axis_color), title_font=dict(color=_axis_color)),
                    yaxis=dict(tickfont=dict(size=12, color=_axis_color), title_font=dict(color=_axis_color)),
                    coloraxis_colorbar=dict(tickfont=dict(size=12, color=_axis_color), titlefont=dict(size=12, color=_axis_color)),
                )
                st.plotly_chart(fig_hm, use_container_width=True, config={"displayModeBar": False})
        with c_tbl:
            show = gdf.copy()
            if "payback_years" in show.columns:
                show = show.sort_values("payback_years")
            cols = [
                c
                for c in (
                    "fve_kwp",
                    "bateria_kwh",
                    "payback_years",
                    "annual_operating_savings_eur",
                    "npv_eur",
                    "total_capex_eur",
                )
                if c in show.columns
            ]
            top = show[cols].head(12).copy()
            top = top.rename(
                columns={
                    "fve_kwp": "FVE kWp",
                    "bateria_kwh": "Bat. kWh",
                    "payback_years": "Návr. (r.)",
                    "annual_operating_savings_eur": "Úspora/rok",
                    "npv_eur": "NPV",
                    "total_capex_eur": "CAPEX",
                }
            )
            for c in top.columns:
                if c != "Návr. (r.)":
                    top[c] = top[c].apply(lambda x: f"{float(x):,.0f}".replace(",", " ") if pd.notna(x) else "—")
                else:
                    top[c] = top[c].apply(lambda x: f"{float(x):.2f}" if pd.notna(x) else "—")
            st.markdown(
                '<p style="font-size:0.92rem;color:#64748b;margin:0.2rem 0 0.35rem 0;">'
                "Top 12 variantov podľa návratnosti (min. 200 kWp / 250 kWh)</p>",
                unsafe_allow_html=True,
            )
            st.markdown(_html_table_wide(top), unsafe_allow_html=True)

    note = (ctx["cfo"].get("scenario_summary") or "").replace("**", "")
    st.markdown(
        f"""
        <div class="cfo-footnote">
        <b>Záver:</b> {note[:320]}{'…' if len(note) > 320 else ''}
        &nbsp;|&nbsp; NPV = čistá súčasná hodnota budúcich peňažných tokov po diskonte.
        &nbsp;|&nbsp; Zdroj: Domino workflow, bez škálovania záťaže.
        </div>
        """,
        unsafe_allow_html=True,
    )
