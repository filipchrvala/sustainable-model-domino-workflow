from __future__ import annotations

from typing import Optional

try:
    from common.onedata_models import OneDataSecretsModel, RunIdInputMixin
except ModuleNotFoundError:
    from pieces.common.onedata_models import OneDataSecretsModel, RunIdInputMixin


from pydantic import BaseModel, Field


class InputModel(RunIdInputMixin):
    predictions_csv: str = Field(description="CSV with prediction_load_kw and optionally load_kw")


class SecretsModel(OneDataSecretsModel):
    pass



class OutputModel(BaseModel):
    report_json: str
    daily_csv: str
    message: str
