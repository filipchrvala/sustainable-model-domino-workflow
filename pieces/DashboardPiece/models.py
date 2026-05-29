from pydantic import BaseModel, Field

METRIC_HELP: dict[str, str] = {
    "savings_period": "Úspora na nákladoch za elektrinu počas simulovaného obdobia.",
    "capex": "Jednorazová investícia do FVE a batérie (€).",
    "payback": "Návratnosť investície v rokoch (jednoduchá – CAPEX deleno ročná úspora).",
    "npv": (
        "NPV (čistá súčasná hodnota) – súčet budúcich úspor a nákladov prepočítaný na dnešok "
        "diskontnou sadzbou. Kladné NPV znamená, že investícia ekonomicky prekoná alternatívu "
        "(napr. neinvestovať); záporné NPV pri kladnej jednoduchej návratnosti znamená, že úspory "
        "sú reálne, ale pri danej sadzbe a horizonte ešte neprekonajú požadovanú výnosnosť."
    ),
    "annual_savings": "Ročná prevádzková úspora po zavedení FVE a batérie oproti baseline (extrapolácia z obdobia simulácie).",
    "target_payback": "Cieľová doba návratnosti z formulára (roky).",
    "achieved_payback": "Dosiahnutá návratnosť odporúčaného variantu (roky).",
    "recommended_kwp": "Odporúčaný výkon FVE (kWp).",
    "recommended_kwh": "Odporúčaná kapacita batérie (kWh).",
    "capex_fve_bess": "CAPEX FVE + batéria (€).",
    "annual_savings_inv": "Ročná prevádzková úspora (€).",
    "npv_inv": "NPV odporúčaného variantu (€).",
    "cost_baseline": "Ročné prevádzkové náklady na elektrinu bez FVE a batérie (extrapolácia).",
    "cost_with_pv_bess": "Ročné náklady po zavedení odporúčanej FVE a batérie.",
    "grid_pick": "Výber jedného variantu z auto mriežky na porovnanie.",
    "grid_fve_kwp": "Výkon fotovoltiky v kilowattoch peak (kWp).",
    "grid_battery_kwh": "Kapacita batérie v kilowatthodinách (kWh).",
    "grid_payback": "Jednoduchá návratnosť daného variantu.",
    "grid_npv": "NPV daného variantu z mriežky.",
    "rv_potential": "Odhadovaný priestor na zníženie rezervovanej kapacity (RV) po optimalizácii špičiek.",
}


class InputModel(BaseModel):
    report_json: str = Field(description="Path to mrk_savings_report.json")
    kpi_results_csv: str = Field(description="Path to kpi_results.csv")
    investment_evaluation_csv: str = Field(description="Path to investment_evaluation.csv")
    anomaly_alerts_csv: str | None = Field(default=None, description="Optional path to anomaly_alerts.csv")
    drift_report_json: str | None = Field(default=None, description="Optional path to drift_report.json")


class OutputModel(BaseModel):
    dashboard_data_json: str
