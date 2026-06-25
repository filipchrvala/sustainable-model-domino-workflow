from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class InputModel(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    history_csv: str = Field(description="Merged long-term history CSV")
    model_registry_dir: str = Field(description="Directory for per-department model artifacts")
    incremental_window_days: int = Field(default=30, ge=1, description="Train update only on recent window in days")
    full_retrain_every_n_updates: int = Field(
        default=20, ge=1, description="Run full retrain after this many incremental updates"
    )
    incremental_trees: int = Field(default=50, ge=10, description="Number of trees appended in incremental update")


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
    models_index_json: str
    training_summary_json: str
