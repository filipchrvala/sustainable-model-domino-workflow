from typing import Optional

try:
    from common.onedata_models import OneDataSecretsModel, RunIdInputMixin
except ModuleNotFoundError:
    from pieces.common.onedata_models import OneDataSecretsModel, RunIdInputMixin


from pydantic import BaseModel, Field


class InputModel(RunIdInputMixin):
    scenario_yaml: str = Field(description="Path to scenario YAML")


class SecretsModel(OneDataSecretsModel):
    pass



class OutputModel(BaseModel):
    message: str
    pv_catalog_json: str
    inverter_catalog_json: str
    battery_catalog_json: str
    catalog_manifest_json: str
    url_outage_detected: bool
