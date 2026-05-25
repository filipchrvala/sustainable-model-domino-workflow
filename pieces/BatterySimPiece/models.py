from pydantic import BaseModel, Field


class InputModel(BaseModel):
    load_csv: str = Field(description="Path to historical load CSV")
    scenario_yaml: str = Field(description="Path to sized scenario YAML")
    virtual_solar_csv: str = Field(description="Path to virtual_solar.csv")


class OutputModel(BaseModel):
    message: str
    virtual_battery_soc_csv: str
    battery_summary_csv: str
