from pydantic import BaseModel, Field


class InputModel(BaseModel):
    report_json: str = Field(description="Path to mrk_savings_report.json")
    kpi_results_csv: str = Field(description="Path to kpi_results.csv")


class OutputModel(BaseModel):
    message: str
    investment_evaluation_csv: str
    investment_evaluation_json: str
