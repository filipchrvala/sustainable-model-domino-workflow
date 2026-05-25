from pydantic import BaseModel, Field


class InputModel(BaseModel):
    scenario_yaml: str = Field(description="Path to scenario YAML")


class OutputModel(BaseModel):
    message: str
    pv_catalog_json: str
    inverter_catalog_json: str
    battery_catalog_json: str
    catalog_manifest_json: str
    url_outage_detected: bool
