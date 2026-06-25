from __future__ import annotations

import json
from pathlib import Path
import traceback

import numpy as np
import yaml
try:
    from domino.base_piece import BasePiece
except ModuleNotFoundError:
    from local_compat.base_piece import BasePiece

from .models import InputModel, OutputModel

print("[INFO] BatteryStrategyOptimizerPiece module loaded", flush=True)

try:
    from common import onedata_io as od
    from common import mrk_helpers as mrk
    from common import piece_bootstrap as boot
except ModuleNotFoundError:
    try:
        from pieces.common import onedata_io as od
        from pieces.common import mrk_helpers as mrk
        from pieces.common import piece_bootstrap as boot
    except ModuleNotFoundError:
        od = None
        mrk = None
        boot = None


class BatteryStrategyOptimizerPiece(BasePiece):
    """Build simple price-driven strategy thresholds for battery operation."""

    def piece_function(self, input_data: InputModel, secrets_data=None) -> OutputModel:
        if boot is not None:
            boot.bootstrap_log(self.results_path, "BatteryStrategyOptimizerPiece", "piece_function started")
            boot.bootstrap_log(
                self.results_path,
                "BatteryStrategyOptimizerPiece",
                f"inputs load_csv={input_data.load_csv!r} scenario_yaml={input_data.scenario_yaml!r}",
            )
        else:
            print("[INFO] BatteryStrategyOptimizerPiece started", flush=True)
        _stage = None
        if od is not None:
            try:
                input_data, _stage = od.stage_inputs(input_data, secrets_data)
            except Exception as exc:
                if boot is not None:
                    boot.bootstrap_log(self.results_path, "BatteryStrategyOptimizerPiece", f"stage_inputs FAILED: {exc}")
                if od is not None:
                    od.cleanup_on_error(self.results_path, secrets_data, "BatteryStrategyOptimizerPiece", _stage)
                raise
        _piece_out = None
        try:
            csv_path = Path(input_data.load_csv)
            scenario_path = Path(input_data.scenario_yaml)
            out_dir = Path(self.results_path or scenario_path.parent)
            out_dir.mkdir(parents=True, exist_ok=True)
            log_path = out_dir / "battery_strategy_optimizer.log"

            def _log(msg: str) -> None:
                text = f"[BatteryStrategyOptimizerPiece] {msg}"
                print(text, flush=True)
                with log_path.open("a", encoding="utf-8") as f:
                    f.write(text + "\n")

            _log(f"Input load_csv={csv_path}")
            _log(f"Input scenario_yaml={scenario_path}")
            if not csv_path.is_file():
                raise FileNotFoundError(f"Load CSV not found: {csv_path}")
            if not scenario_path.is_file():
                raise FileNotFoundError(f"Scenario YAML not found: {scenario_path}")

            try:
                if mrk is None:
                    raise RuntimeError("mrk_helpers not available")
                cfg = yaml.safe_load(scenario_path.read_text(encoding="utf-8")) or {}
                df = mrk.load_consumption_csv(csv_path)
                price = mrk.build_price_series(df, cfg).values.astype(float)
                rec = {
                    "charge_below_eur_per_kwh": round(float(np.quantile(price, 0.30)), 6),
                    "discharge_above_eur_per_kwh": round(float(np.quantile(price, 0.75)), 6),
                    "expensive_hour_threshold_eur_per_kwh": round(float(np.percentile(price, 70.0)), 6),
                    "strategy_note": "Thresholds aligned to dispatch logic in SimulatePiece.",
                }
                _log(f"Computed thresholds from rows={len(df)}")
            except Exception as exc:
                (out_dir / "battery_strategy_optimizer_error.txt").write_text(traceback.format_exc(), encoding="utf-8")
                _log(f"ERROR during strategy optimization: {exc}")
                raise

            out_json = out_dir / "battery_strategy_recommendation.json"
            out_json.write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
            _log(f"Wrote output: {out_json}")
            _piece_out = OutputModel(
                message="Battery strategy optimized",
                battery_strategy_recommendation_json=str(out_json),
            )
        finally:
            if od is not None and _piece_out is None:
                od.cleanup_on_error(self.results_path, secrets_data, "BatteryStrategyOptimizerPiece", _stage)
            elif _stage is not None:
                _stage.cleanup()
        if od is not None and _piece_out is not None:
            return od.finish_piece(_piece_out, self.results_path, secrets_data, "BatteryStrategyOptimizerPiece", _stage)
        return _piece_out
