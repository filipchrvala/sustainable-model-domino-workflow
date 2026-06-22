from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class InputModel(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    history_csv: str = Field(description="Merged history CSV")
    models_index_json: str = Field(description="JSON map department -> model path")
    model_registry_dir: str = Field(description="Allowed model registry root for secure loading")
    horizon_hours: int = Field(default=24, ge=1, description="Forecast horizon in hours")


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
    forecast_csv: str
