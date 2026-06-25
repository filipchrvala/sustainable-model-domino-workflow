from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class InputModel(BaseModel):
    data_path: str = Field(
        title="Training dataset path",
        description="Path to preprocessed parquet or CSV dataset"
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
    model_config = ConfigDict(protected_namespaces=())

    message: str = Field(
        description="Training result message"
    )
    model_file_path: str = Field(
        description="Path to trained model file"
    )
    train_log_path: str = Field(
        description="Path to training log file"
    )
