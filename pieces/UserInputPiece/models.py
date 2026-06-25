from typing import Optional

try:
    from common.onedata_models import OneDataSecretsModel, RunIdInputMixin
except ModuleNotFoundError:
    from pieces.common.onedata_models import OneDataSecretsModel, RunIdInputMixin


from pydantic import BaseModel, Field


class InputModel(RunIdInputMixin):
    load_csv: str = Field(description="Path to historical load CSV")
    prices_csv: str = Field(default="", description="Optional path to historical prices CSV")
    scenario_yaml: str = Field(description="Path to scenario YAML")


class SecretsModel(OneDataSecretsModel):
    pass



class OutputModel(BaseModel):
    message: str
    load_csv: str
    scenario_yaml: str
    workflow_user_input_json: str
    run_id: str = ""
