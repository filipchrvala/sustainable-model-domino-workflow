from typing import Optional

try:
    from common.onedata_models import OneDataSecretsModel, RunIdInputMixin
except ModuleNotFoundError:
    from pieces.common.onedata_models import OneDataSecretsModel, RunIdInputMixin


from pydantic import BaseModel, Field


class InputModel(RunIdInputMixin):
    report_json: str = Field(description="Path to mrk_savings_report.json")
    kpi_results_csv: str = Field(description="Path to kpi_results.csv")


class SecretsModel(OneDataSecretsModel):
    pass



class OutputModel(BaseModel):
    message: str
    investment_evaluation_csv: str
    investment_evaluation_json: str
