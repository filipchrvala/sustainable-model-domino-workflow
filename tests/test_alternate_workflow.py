"""Smoke test: Alternate `run_workflow.py` (rýchla investičná fáza)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_run_workflow_exits_zero():
    r = subprocess.run(
        [sys.executable, str(ROOT / "run_workflow.py"), "--phase", "investment"],
        cwd=str(ROOT),
    )
    assert r.returncode == 0
    assert (ROOT / "tests" / "user_input" / "workflow_user_input.json").is_file()
    assert (ROOT / "tests" / "TechnicalLimitsPiece_Input" / "technical_limits_input.json").is_file()
    assert (ROOT / "tests" / "SizingOptimizationPiece_Input" / "sizing_optimization_input.json").is_file()
    assert (ROOT / "tests" / "FeasibilityReportPiece_Input" / "feasibility_report_input.json").is_file()
    assert (ROOT / "tests" / "_generated" / "scenario.yml").is_file()
    assert (ROOT / "tests" / "_generated" / "battery_config.yml").is_file()
    assert (ROOT / "tests" / "UserInputPiece_Output" / "user_input_output.json").is_file()
    assert (ROOT / "tests" / "TechnicalLimitsPiece_Output" / "technical_limits_output.json").is_file()
    assert (ROOT / "tests" / "SizingOptimizationPiece_Output" / "sizing_optimization_output.json").is_file()
    assert (ROOT / "tests" / "FeasibilityReportPiece_Outputs" / "feasibility_report.json").is_file()


def test_run_full_workflow_generates_monitoring_and_strategy():
    r = subprocess.run(
        [sys.executable, str(ROOT / "run_workflow.py")],
        cwd=str(ROOT),
    )
    assert r.returncode == 0
    assert (ROOT / "tests" / "ModelMonitoringPiece_Outputs" / "monitoring_report.json").is_file()
    assert (ROOT / "tests" / "ModelMonitoringPiece_Outputs" / "A" / "monitoring_report.json").is_file()
    assert (ROOT / "tests" / "ModelMonitoringPiece_Outputs" / "B" / "monitoring_report.json").is_file()
    assert (ROOT / "tests" / "TrainModelPiece_Outputs" / "models_by_department.json").is_file()
    assert (ROOT / "tests" / "PredictPiece_Outputs" / "predictions_by_department.csv").is_file()
    assert (
        ROOT / "tests" / "BatteryStrategyOptimizerPiece_Outputs" / "battery_strategy_recommendation.json"
    ).is_file()
    assert (ROOT / "tests" / "dashboard_data.json").is_file()
