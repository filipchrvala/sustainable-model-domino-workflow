from __future__ import annotations

import json
from pathlib import Path
import traceback

import pandas as pd
try:
    from domino.base_piece import BasePiece
except ModuleNotFoundError:
    from local_compat.base_piece import BasePiece

from .models import InputModel, OutputModel


class InvestmentEvalPiece(BasePiece):
    """Investment metrics from report + KPI."""

    def piece_function(self, input_data: InputModel) -> OutputModel:
        rep_path = Path(input_data.report_json)
        kpi_path = Path(input_data.kpi_results_csv)
        out_dir = Path(self.results_path or rep_path.parent)
        out_dir.mkdir(parents=True, exist_ok=True)
        log_path = out_dir / "investment_eval.log"

        def _log(msg: str) -> None:
            text = f"[InvestmentEvalPiece] {msg}"
            print(text, flush=True)
            with log_path.open("a", encoding="utf-8") as f:
                f.write(text + "\n")

        _log(f"Input report_json={rep_path}")
        _log(f"Input kpi_results_csv={kpi_path}")
        if not rep_path.is_file():
            raise FileNotFoundError(f"Report JSON not found: {rep_path}")
        if not kpi_path.is_file():
            raise FileNotFoundError(f"KPI CSV not found: {kpi_path}")

        try:
            rep = json.loads(rep_path.read_text(encoding="utf-8"))
            kpi = pd.read_csv(kpi_path).iloc[0].to_dict()

            pv = rep["scenarios"].get("pv_only") or {}
            both = rep["scenarios"].get("optimized") or rep["scenarios"].get("pv_and_battery") or {}
            sav = (
                rep["savings_vs_baseline"].get("optimized")
                or rep["savings_vs_baseline"].get("pv_and_battery")
                or {}
            )
            cap = rep.get("capex_inputs") or {}
            exec_ = rep.get("executive_summary") or {}
            inv_eq = (rep.get("equipment") or {}).get("investment_metrics") or {}
            annual_est = exec_.get("operating_savings_eur_per_year_estimate")
            if annual_est is not None:
                annual_sav = float(annual_est)
            else:
                annual_sav = float(sav.get("operating_savings_eur_vs_baseline", 0.0))

            row = {
                "annual_savings_eur": annual_sav,
                "operating_savings_period_eur": float(
                    exec_.get("operating_savings_eur_period", sav.get("operating_savings_eur_vs_baseline", 0.0))
                ),
                "net_after_capex_savings_eur": float(sav.get("net_after_capex_savings_eur_vs_baseline", 0.0)),
                "pv_capex_eur": float(cap.get("pv_capex_eur", 0.0)),
                "battery_capex_eur": float(cap.get("battery_capex_eur", 0.0)),
                "total_capex_eur": float(cap.get("pv_capex_eur", 0.0)) + float(cap.get("battery_capex_eur", 0.0)),
                "pv_only_operating_eur": float(pv.get("total_operating_eur", 0.0)),
                "pv_battery_operating_eur": float(both.get("total_operating_eur", 0.0)),
                "battery_cycles_est": float(kpi.get("battery_equivalent_full_cycles", 0.0)),
                "simple_payback_years": inv_eq.get("simple_payback_years"),
                "discounted_payback_years": inv_eq.get("discounted_payback_years"),
                "npv_operating_eur": inv_eq.get("npv_eur"),
            }

            out_csv = out_dir / "investment_evaluation.csv"
            out_json = out_dir / "investment_evaluation.json"
            pd.DataFrame([row]).to_csv(out_csv, index=False)
            out_json.write_text(json.dumps({"investment_evaluation": [row]}, indent=2, ensure_ascii=False), encoding="utf-8")
            _log(f"Wrote outputs: {out_csv}, {out_json}")
            return OutputModel(
                message="Investment evaluation finished",
                investment_evaluation_csv=str(out_csv),
                investment_evaluation_json=str(out_json),
            )
        except Exception as exc:
            (out_dir / "investment_eval_error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            _log(f"ERROR during investment evaluation: {exc}")
            raise
