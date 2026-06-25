from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class InputModel(BaseModel):
    workflow_user_input_json: str = Field(description="Path to workflow_user_input.json")
    sized_scenario_yaml: str = Field(description="Path to sized scenario YAML")
    sizing_optimization_json: str = Field(description="Path to sizing optimization JSON")
    investment_evaluation_csv: str = Field(
        default="",
        description="Optional path to investment_evaluation.csv for simulation-backed metrics",
    )


class SecretsModel(BaseModel):
    """Optional OneData credentials and output target. When host+token are set,
    onedata:/// input paths are read from OneData and all outputs are mirrored to
    <onedata_output_dir>/<PieceName>/. When absent, the piece runs locally."""

    onedata_onezone_host: Optional[str] = Field(
        default=None, description="Onedata Onezone host, e.g. data.spice-platform.eu")
    onedata_token: Optional[str] = Field(
        default=None, description="Onedata access token.")
    onedata_output_dir: Optional[str] = Field(
        default=None, description="OneData base dir for outputs, e.g. onedata:///FilipsSpace/run")


class OutputModel(BaseModel):
    feasible: bool
    target_payback_years: float
    recommended_kwp: float
    recommended_kwh: float
    achieved_payback_years: float
    minimum_payback_in_search_space_years: float
    message: str
    cfo_notes: dict
