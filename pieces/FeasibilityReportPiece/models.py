from __future__ import annotations

from typing import Optional

try:
    from common.onedata_models import OneDataSecretsModel, RunIdInputMixin
except ModuleNotFoundError:
    from pieces.common.onedata_models import OneDataSecretsModel, RunIdInputMixin


from pydantic import BaseModel, Field


class InputModel(RunIdInputMixin):
    workflow_user_input_json: str = Field(description="Path to workflow_user_input.json")
    sized_scenario_yaml: str = Field(description="Path to sized scenario YAML")
    sizing_optimization_json: str = Field(description="Path to sizing optimization JSON")
    investment_evaluation_csv: str = Field(
        default="",
        description="Optional path to investment_evaluation.csv for simulation-backed metrics",
    )


class SecretsModel(OneDataSecretsModel):
    pass



class OutputModel(BaseModel):
    feasible: bool
    target_payback_years: float
    recommended_kwp: float
    recommended_kwh: float
    achieved_payback_years: float
    minimum_payback_in_search_space_years: float
    message: str
    cfo_notes: dict
