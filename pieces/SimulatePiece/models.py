from typing import Optional

from pydantic import BaseModel, Field


class InputModel(BaseModel):
    load_csv: str = Field(description="Path to historical load CSV")
    scenario_yaml: str = Field(description="Path to scenario YAML")
    output_dir: str = Field(default="", description="Optional output dir when results_path is not set")
    virtual_battery_soc_csv: str = Field(
        default="",
        description="Optional battery SOC CSV produced by BatterySimPiece",
    )
    battery_summary_csv: str = Field(
        default="",
        description="Optional battery summary CSV produced by BatterySimPiece",
    )
    battery_strategy_recommendation_json: str = Field(
        default="",
        description="Optional battery strategy recommendation JSON",
    )
    ranked_catalog_json: str = Field(default="", description="Optional ranked catalog recommendation JSON")
    inverter_catalog_json: str = Field(default="", description="Optional inverter catalog JSON")
    battery_catalog_json: str = Field(default="", description="Optional battery catalog JSON")
    catalog_manifest_json: str = Field(default="", description="Optional catalog sync manifest JSON")


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
    message: str
    report_json: str
