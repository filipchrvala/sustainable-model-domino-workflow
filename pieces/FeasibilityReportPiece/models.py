from __future__ import annotations

from pydantic import BaseModel, Field


class InputModel(BaseModel):
    workflow_user_input_json: str = Field(description="Path to workflow_user_input.json")
    sized_scenario_yaml: str = Field(description="Path to sized scenario YAML")
    sizing_optimization_json: str = Field(description="Path to sizing optimization JSON")
    investment_evaluation_csv: str = Field(
        default="",
        description="Optional path to investment_evaluation.csv for simulation-backed metrics",
    )


class OutputModel(BaseModel):
    feasible: bool
    target_payback_years: float
    recommended_kwp: float
    recommended_kwh: float
    achieved_payback_years: float
    minimum_payback_in_search_space_years: float
    message: str
    cfo_notes: dict
