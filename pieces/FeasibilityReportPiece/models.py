from __future__ import annotations

from pydantic import BaseModel


class InputModel(BaseModel):
    constraints: dict
    economics: dict
    best_kwp: float
    best_kwh: float
    best_payback_years: float
    best_annual_savings_eur: float
    best_capex_eur: float
    best_npv_eur: float
    grid: list[dict]
    # Po full run: riadok z investment_evaluation.csv (KPI → časová simulácia)
    simulation_metrics: dict | None = None


class OutputModel(BaseModel):
    feasible: bool
    target_payback_years: float
    recommended_kwp: float
    recommended_kwh: float
    achieved_payback_years: float
    minimum_payback_in_search_space_years: float
    message: str
    cfo_notes: dict
