"""One-off: revert new piece names to pre-rename folders (local workflow only)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPLACEMENTS = [
    ("BatterySimulationPiece", "BatterySimPiece"),
    ("BatteryStrategyPiece", "BatteryStrategyOptimizerPiece"),
    ("SolarSimulationPiece", "SolarSimPiece"),
    ("SimulateMRKScenarioPiece", "SimulatePiece"),
    ("ComputeKPIsPiece", "KPIPiece"),
    ("InvestmentEvaluationPiece", "InvestmentEvalPiece"),
    ("DashboardDataPiece", "DashboardPiece"),
]

SKIP_DIRS = {".git", "__pycache__", "_sync_backup_pre_cost_optimizer", ".pytest_cache"}


def main() -> None:
    for path in ROOT.rglob("*"):
        if path.is_dir() or any(p in SKIP_DIRS for p in path.parts):
            continue
        if path.suffix.lower() not in {".py", ".json", ".yml", ".yaml", ".md", ".ps1"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        orig = text
        for old, new in REPLACEMENTS:
            text = text.replace(old, new)
        if text != orig:
            path.write_text(text, encoding="utf-8")
            print("updated", path.relative_to(ROOT))


if __name__ == "__main__":
    main()
