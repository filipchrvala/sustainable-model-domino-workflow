from typing import Optional

try:
    from common.onedata_models import OneDataSecretsModel, RunIdInputMixin
except ModuleNotFoundError:
    from pieces.common.onedata_models import OneDataSecretsModel, RunIdInputMixin


from pydantic import BaseModel, Field


class InputModel(RunIdInputMixin):
    load_csv: str = Field(description="Path to historical load CSV")
    scenario_yaml: str = Field(description="Path to scenario YAML")
    technical_limits_json: str = Field(description="Path to technical limits json")


class SecretsModel(OneDataSecretsModel):
    pass



class OutputModel(BaseModel):
    message: str
    sized_scenario_yaml: str
    sizing_optimization_json: str
