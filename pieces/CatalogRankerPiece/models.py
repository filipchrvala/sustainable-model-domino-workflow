from pydantic import BaseModel, Field


class InputModel(BaseModel):
    scenario_yaml: str = Field(description="Path to sized scenario YAML")
    pv_catalog_json: str = Field(description="Path to synced PV catalog JSON")


class OutputModel(BaseModel):
    message: str
    catalog_ranked_recommendation_json: str
