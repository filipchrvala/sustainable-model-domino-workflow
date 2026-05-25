from pydantic import BaseModel, Field


class InputModel(BaseModel):
    load_csv: str = Field(description="Path to historical load CSV")
    scenario_yaml: str = Field(description="Path to scenario YAML")


class OutputModel(BaseModel):
    message: str
    technical_limits_json: str
    scenario_yaml: str
