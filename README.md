# Sustainable Model Domino Workflow

Workflow combines:

- load ingest, preprocessing, training, prediction, and model monitoring,
- MRK + PV + battery sizing and simulation,
- investment and dashboard outputs,
- sustainable refresh flow with incremental training, horizon forecasting, and anomaly alerts.

## Local setup

Install runtime dependencies:

```text
pip install -r requirements_0.txt
```

Main entrypoints:

```text
python run_workflow.py
python run_workflow.py --phase investment
python run_workflow.py --phase sustainable --horizon-hours 72
python -m streamlit run scripts/streamlit_dashboard.py
python -m streamlit run scripts/streamlit_web_input.py
```

PowerShell helpers:

```text
.\run_live_dashboard.ps1
.\run_web_input.ps1
```

## Main outputs

- `tests/SimulatePiece_Outputs/mrk_savings_report.json`
- `tests/KPIPiece_Outputs/kpi_results.csv`
- `tests/InvestmentEvalPiece_Outputs/investment_evaluation.csv`
- `tests/DashboardPiece_Outputs/dashboard_data.json`
- `tests/dashboard_data.json`
- `tests/sustainable/outputs/forecast_by_department.csv`
- `tests/AnomalyAlertPiece_Outputs/anomaly_alerts.csv`

## Tests

```text
pip install -r requirements-tests.txt
pytest
```

## Domino

Domino metadata is tracked in:

- `.domino/compiled_metadata.json`
- `.domino/dependencies_map.json`

The repository is intended to expose the full sustainable workflow piece set, with workflow logic kept directly inside real piece folders.
