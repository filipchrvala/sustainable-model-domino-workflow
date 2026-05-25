from pydantic import BaseModel, ConfigDict, Field


class InputModel(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    history_csv: str = Field(description="Merged history CSV")
    models_index_json: str = Field(description="JSON map department -> model path")
    model_registry_dir: str = Field(description="Allowed model registry root for secure loading")
    horizon_hours: int = Field(default=24, ge=1, description="Forecast horizon in hours")


class OutputModel(BaseModel):
    message: str
    forecast_csv: str
