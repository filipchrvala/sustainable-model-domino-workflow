from __future__ import annotations

from pydantic import BaseModel, Field


class InputModel(BaseModel):
    predictions_csv: str = Field(description="CSV with prediction_load_kw and optionally load_kw")


class OutputModel(BaseModel):
    report_json: str
    daily_csv: str
    message: str
