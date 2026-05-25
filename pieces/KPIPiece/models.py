from pydantic import BaseModel, Field


class InputModel(BaseModel):
    report_json: str = Field(description="Path to mrk_savings_report.json")


class OutputModel(BaseModel):
    message: str
    kpi_results_csv: str
