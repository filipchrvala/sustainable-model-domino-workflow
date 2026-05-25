from pydantic import BaseModel, Field


class InputModel(BaseModel):
    load_csv: str = Field(description="Path to historical load CSV")
    scenario_yaml: str = Field(description="Path to scenario YAML")
    technical_limits_json: str = Field(description="Path to technical limits json")


class OutputModel(BaseModel):
    message: str
    sized_scenario_yaml: str
    sizing_optimization_json: str
