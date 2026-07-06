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


class KPIPiece(BasePiece):
    """Extract compact KPI table from MRK report JSON."""

    def piece_function(self, input_data: InputModel) -> OutputModel:
        rep_path = Path(input_data.report_json)
        out_dir = Path(self.results_path or rep_path.parent)
        out_dir.mkdir(parents=True, exist_ok=True)
        log_path = out_dir / "kpi.log"

        def _log(msg: str) -> None:
            text = f"[KPIPiece] {msg}"
            print(text, flush=True)
            with log_path.open("a", encoding="utf-8") as f:
                f.write(text + "\n")

        _log(f"Input report_json={rep_path}")
        if not rep_path.is_file():
            raise FileNotFoundError(f"Report JSON not found: {rep_path}")
        try:
            rep = json.loads(rep_path.read_text(encoding="utf-8"))
            schema = ((rep.get("meta") or {}).get("schema_version") or "mrk_report_v1").strip()
            if schema not in {"mrk_report_v1", "mrk_report_v2"}:
                raise ValueError(f"Unsupported report schema_version: {schema}")

            base = rep["scenarios"]["baseline"]
            both = (
                rep["scenarios"].get("optimized")
                or rep["scenarios"].get("pv_and_battery")
                or {}
            )
            sav = (
                rep["savings_vs_baseline"].get("optimized")
                or rep["savings_vs_baseline"].get("pv_and_battery")
                or {}
            )

            out = {
                "report_schema_version": schema,
                "baseline_operating_eur": float(base.get("total_operating_eur", 0.0)),
                "pv_battery_operating_eur": float(both.get("total_operating_eur", 0.0)),
                "operating_savings_eur": float(sav.get("operating_savings_eur_vs_baseline", 0.0)),
                "net_after_capex_savings_eur": float(sav.get("net_after_capex_savings_eur_vs_baseline", 0.0)),
                "battery_equivalent_full_cycles": float(both.get("equivalent_full_cycles", 0.0)),
                "mrk_baseline_eur": float(base.get("mrk_cost_period_eur", 0.0)),
                "mrk_pv_battery_eur": float(both.get("mrk_cost_period_eur", 0.0)),
            }

            csv_path = out_dir / "kpi_results.csv"
            pd.DataFrame([out]).to_csv(csv_path, index=False)
            _log(f"Wrote KPI CSV: {csv_path}")
            return OutputModel(message="KPI calculation finished", kpi_results_csv=str(csv_path))
        except Exception as exc:
            (out_dir / "kpi_error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            _log(f"ERROR during KPI calculation: {exc}")
            raise
