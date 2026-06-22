from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class InputModel(BaseModel):
    predictions_csv: str = Field(description="CSV with prediction_load_kw and optionally load_kw")


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
    report_json: str
    daily_csv: str
    message: str
