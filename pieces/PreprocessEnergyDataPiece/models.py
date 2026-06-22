from typing import Optional

from pydantic import BaseModel, Field


class InputModel(BaseModel):
    input_path: str = Field(
        description="Path to merged energy parquet file"
    )

    forecast_hours: int = Field(
        default=24,
        description="Ignored when generate_predict_dataset is False",
    )

    generate_predict_dataset: bool = Field(
        default=False,
        description="If False (default): only train_dataset.parquet. Predict uses separate CSV in PredictPiece.",
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
    message: str
    train_file_path: str
    predict_file_path: str = Field(
        default="",
        description="Empty if generate_predict_dataset is False",
    )
