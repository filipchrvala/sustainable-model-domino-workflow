from pydantic import BaseModel, Field

METRIC_HELP: dict[str, str] = {
    "savings_period": "Úspora na nákladoch za elektrinu počas simulovaného obdobia.",
    "capex": "Jednorazová investícia do FVE a batérie (€).",
    "payback": "Návratnosť investície v rokoch.",
    "npv": "Čistá súčasná hodnota (NPV) v €.",
    "target_payback": "Cieľová doba návratnosti z formulára (roky).",
    "achieved_payback": "Dosiahnutá návratnosť odporúčaného variantu (roky).",
    "recommended_kwp": "Odporúčaný výkon FVE (kWp).",
    "recommended_kwh": "Odporúčaná kapacita batérie (kWh).",
    "capex_fve_bess": "CAPEX FVE + batéria (€).",
    "annual_savings_inv": "Ročná prevádzková úspora (€).",
    "npv_inv": "NPV odporúčaného variantu (€).",
}


class InputModel(BaseModel):
    report_json: str = Field(description="Path to mrk_savings_report.json")
    kpi_results_csv: str = Field(description="Path to kpi_results.csv")
    investment_evaluation_csv: str = Field(description="Path to investment_evaluation.csv")
    anomaly_alerts_csv: str | None = Field(default=None, description="Optional path to anomaly_alerts.csv")
    drift_report_json: str | None = Field(default=None, description="Optional path to drift_report.json")


class OutputModel(BaseModel):
    dashboard_data_json: str
