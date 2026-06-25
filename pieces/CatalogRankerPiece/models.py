from typing import Optional

try:
    from common.onedata_models import OneDataSecretsModel, RunIdInputMixin
except ModuleNotFoundError:
    from pieces.common.onedata_models import OneDataSecretsModel, RunIdInputMixin


from pydantic import BaseModel, Field


class InputModel(RunIdInputMixin):
    scenario_yaml: str = Field(description="Path to sized scenario YAML")
    pv_catalog_json: str = Field(description="Path to synced PV catalog JSON")


class SecretsModel(OneDataSecretsModel):
    pass



class OutputModel(BaseModel):
    message: str
    catalog_ranked_recommendation_json: str
