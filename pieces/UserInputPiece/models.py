from pydantic import BaseModel, Field


class InputModel(BaseModel):
    load_csv: str = Field(description="Path to historical load CSV")
    prices_csv: str = Field(default="", description="Optional path to historical prices CSV")
    scenario_yaml: str = Field(description="Path to scenario YAML")


class OutputModel(BaseModel):
    message: str
    load_csv: str
    scenario_yaml: str
