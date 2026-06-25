from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class InputModel(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_path: str = Field(description="Path to trained XGBoost model")
    data_path: str = Field(description="Path to prediction dataset (15min)")
    use_rolling_prediction: bool = Field(
        default=True,
        description="True (default): bridge_rows of real load_kw, then lags from prior predictions.",
    )
    bridge_rows: int = Field(default=4, ge=1)


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
    prediction_file_path: str
    runtime_load_csv: str = Field(
        description="Load CSV for MRK sizing/simulation (load_kw from predictions)",
    )
