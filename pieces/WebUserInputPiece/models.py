from pydantic import BaseModel, Field

# --- field help (web formulár) ---

H: dict[str, str] = {
    "site_name": (
        "Názov vašej prevádzky, fabriky alebo projektu (napr. „Výrobný závod Trnava“). "
        "Zobrazí sa v prehľadoch, reportoch o uskutočniteľnosti investície a na dashboarde."
    ),
    "site_latitude": (
        "Zemepisná šírka miesta inštalácie (súradnica sever–juh). Spolu s dĺžkou určuje polohu "
        "pre odhad výroby FVE (fotovoltaika)."
    ),
    "site_longitude": (
        "Zemepisná dĺžka miesta inštalácie (súradnica východ–západ). Musí byť zadaná spolu so šírkou."
    ),
    "target_payback_years": (
        "Koľko rokov maximálne chcete čakať na návratnosť investície do FVE a batérie."
    ),
    "max_roof_area_m2": (
        "Plocha strechy pre panely (m²). Obmedzuje horný limit výkonu FVE (kWp)."
    ),
    "max_battery_area_m2": (
        "Plocha pre batériu (m²). Spolu s hustotou určí max. kapacitu v kWh."
    ),
    "kwh_per_m2_battery_area": (
        "Koľko kWh kapacity batérie na 1 m² vyhradenej plochy (typicky 1,5–3)."
    ),
    "eur_per_kwp": "Investičný CAPEX fotovoltaiky v € na 1 kWp inštalovaného výkonu.",
    "yield_kwh_per_kwp_year": "Očakávaný ročný výnos FVE v kWh na 1 kWp (podľa polohy a profilu).",
    "eur_per_kwh": "Investičný CAPEX batérie v € na 1 kWh kapacity.",
    "mount_type": "Typ montáže panelov: strecha (roof) alebo zem (ground).",
    "shading": "Odhad tieňovania: none / low / medium / high — ovplyvňuje výnos FVE.",
    "annual_load_mwh": (
        "Súhrn ročnej spotreby z CSV — simulácia používa celú časovú radu, nie toto jedno číslo."
    ),
    "annual_load_mwh_manual": (
        "Len ak nemáte CSV — hrubý odhad ročnej spotreby v MWh."
    ),
    "load_csv": (
        "CSV so spotrebou: stĺpec času a load_kw (kW). Môže obsahovať aj cenu €/kWh."
    ),
    "prices_csv": (
        "Voliteľný CSV s cenami. Ak chýba, ceny musia byť v súbore spotreby."
    ),
    "append_to_drop": "Pri uložení pošle nové dáta do histórie pre ďalšie behy workflow.",
    "append_csv": "Doplnkový CSV s novými riadkami spotreby.",
    "manual_datetime": "Čas merania (typ. krok 15 min).",
    "manual_load_kw": "Okamžitý odber v kW v danom čase.",
    "manual_price": "Cena elektriny v €/kWh.",
    "timestep_minutes": "Krok časovej rady v minútach (zvyčajne 15). Po nahratí CSV sa doplní sám.",
    "mrk_peak_from_csv": "Najvyššia mesačná špička odberu z CSV — návrh pre zmluvný výkon RV.",
    "contract_kw": (
        "Zmluvný rezervovaný výkon RV (kW) u distribútora — mesačný poplatok a penalizácie."
    ),
    "fee_eur_per_kw_month": "Poplatok za 1 kW RV za mesiac (€).",
    "excess_peak_penalty_eur_per_kw": "Penalizácia za každý kW nad RV (€/kW).",
    "selection_mode": "auto = mriežka variantov; manual = presné kWp a kWh.",
    "system_scope": "Čo simulovať: FVE, batéria, alebo oboje.",
    "installed_kwp": "Manuálny výkon FVE v kWp.",
    "energy_kwh": "Manuálna kapacita batérie v kWh.",
    "max_c_rate": "Rýchlosť nabíjania/vybíjania batérie (násobok kapacity).",
    "grid_kwp_min": "Spodná hranica FVE (kWp) v mriežke variantov.",
    "grid_kwp_max": "Horná hranica FVE (kWp) v mriežke.",
    "grid_kwp_step": "Krok FVE (kWp) v mriežke.",
    "grid_kwh_min": "Spodná hranica batérie (kWh) v mriežke.",
    "grid_kwh_max": "Horná hranica batérie (kWh) v mriežke.",
    "grid_kwh_step": "Krok batérie (kWh) v mriežke.",
    "grid_respect_physical": "Obmedziť mriežku fyzickými limitmi plochy a CAPEX.",
    "auto_objective": "max_npv alebo shortest_payback pri auto výbere variantu.",
    "max_configurations": "Max. počet kombinácií FVE × batéria.",
    "kwp_step": "Krok FVE pri auto optimalizácii (záložný).",
    "kwh_step": "Krok batérie pri auto optimalizácii (záložný).",
    "min_pv_kwp": "Minimálny výkon FVE pre auto návrh.",
    "min_battery_kwh": "Minimálna batéria pre auto návrh.",
    "discount_rate": "Diskontná sadzba pre NPV (napr. 0,08 = 8 %).",
    "amortization_years": "Horizont analýzy v rokoch.",
    "finance_enabled": "Podrobný finančný model (úver, daň, OPEX).",
    "debt_ratio_of_capex": "Podiel investície financovaný úverom (0–1).",
    "trading_only": "Dodatočný scenár iba batérie bez FVE.",
    "c_rate_sweep": "Porovnanie viacerých C-rate batérie.",
    "btn_save": "Uloží formulár bez spustenia výpočtu.",
    "btn_validate": "Uloží a skontroluje CSV a konfiguráciu.",
    "btn_run_workflow": "Uloží a spustí celý workflow (~18 krokov).",
}

FIELD_LABELS: dict[str, str] = {
    "site_name": "Názov prevádzky",
    "site_latitude": "Zemepisná šírka",
    "site_longitude": "Zemepisná dĺžka",
    "target_payback_years": "Cieľová návratnosť (roky)",
    "max_roof_area_m2": "Max. plocha strechy (m²)",
    "max_battery_area_m2": "Max. plocha batérie (m²)",
    "kwh_per_m2_battery_area": "Hustota batérie (kWh/m²)",
    "annual_load_mwh": "Ročná spotreba z CSV (MWh)",
    "annual_load_mwh_manual": "Ročná spotreba bez CSV",
    "load_csv": "Súbor spotreby (CSV)",
    "prices_csv": "Súbor cien (CSV)",
    "append_to_drop": "Pridať do histórie",
    "append_csv": "Doplnkový CSV",
    "manual_datetime": "Čas merania",
    "manual_load_kw": "Odber (kW)",
    "manual_price": "Cena (€/kWh)",
    "timestep_minutes": "Krok dát (min)",
    "mrk_peak_from_csv": "Mes. špička z CSV",
    "contract_kw": "RV (kW)",
    "fee_eur_per_kw_month": "Poplatok RV (€/kW/mes)",
    "excess_peak_penalty_eur_per_kw": "Penalizácia (€/kW)",
    "selection_mode": "Režim návrhu",
    "system_scope": "Rozsah technológií",
    "installed_kwp": "FVE (kWp)",
    "energy_kwh": "Batéria (kWh)",
    "max_c_rate": "C-rate",
    "grid_kwp_min": "Mriežka min FVE",
    "grid_kwp_max": "Mriežka max FVE",
    "grid_kwp_step": "Mriežka krok FVE",
    "grid_kwh_min": "Mriežka min bat.",
    "grid_kwh_max": "Mriežka max bat.",
    "grid_kwh_step": "Mriežka krok bat.",
    "grid_respect_physical": "Len fyzické limity",
    "auto_objective": "Cieľ auto voľby",
    "max_configurations": "Max. kombinácií",
    "kwp_step": "Krok kWp",
    "kwh_step": "Krok kWh",
    "min_pv_kwp": "Min. FVE",
    "min_battery_kwh": "Min. batéria",
    "discount_rate": "Diskontná sadzba",
    "amortization_years": "Horizont (r.)",
    "finance_enabled": "Finance layer",
    "debt_ratio_of_capex": "Podiel úveru",
    "trading_only": "Trading-only",
    "c_rate_sweep": "C-rate sweep",
    "btn_save": "Uložiť",
    "btn_validate": "Validovať",
    "btn_run_workflow": "Spustiť workflow",
}

FIELD_HELP = H


class InputModel(BaseModel):
    """Domino piece input – reads saved web form state and materializes workflow files."""

    web_form_state_json: str = Field(
        description="Path to web_form_state.json (from Streamlit WebUserInputPiece UI)",
    )
    scenario_yaml: str = Field(
        description="Scenario YAML path (usually tests/_generated/scenario.yml after materialize)",
    )
    use_classic_csv_fallback: bool = Field(
        default=False,
        description="If true and web CSV paths missing, use FetchEnergyDataPiece_Inputs CSV files",
    )


class OutputModel(BaseModel):
    message: str
    load_csv: str
    scenario_yaml: str
    workflow_user_input_json: str
    web_form_state_json: str
    input_mode: str = "web"
