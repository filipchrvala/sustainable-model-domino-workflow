from __future__ import annotations

import copy
import json
from pathlib import Path
import traceback

import yaml
try:
    from domino.base_piece import BasePiece
except ModuleNotFoundError:
    from local_compat.base_piece import BasePiece

from .models import InputModel, OutputModel

try:
    from common import onedata_io as od
    from common.simulate_bridge import load_simulate_module
except ModuleNotFoundError:
    try:
        from pieces.common import onedata_io as od
        from pieces.common.simulate_bridge import load_simulate_module
    except ModuleNotFoundError:
        od = None

        def load_simulate_module(*, caller: str = "piece"):
            raise RuntimeError("simulate_bridge not available")


def _require_path(field: str, value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(
            f"Missing upstream input '{field}' (empty path). "
            "Re-import test_sus_onedata.customization and ensure Predict + TechnicalLimits completed."
        )
    return text


class SizingOptimizationPiece(BasePiece):
    """Resolve final scenario sizing (manual or auto)."""

    def piece_function(self, input_data: InputModel, secrets_data=None) -> OutputModel:
        print("[INFO] SizingOptimizationPiece started", flush=True)
        _stage = None
        if od is not None:
            input_data, _stage = od.stage_inputs(input_data, secrets_data)
        _piece_out = None
        try:
            load_csv = _require_path("load_csv", input_data.load_csv)
            scenario_yaml = _require_path("scenario_yaml", input_data.scenario_yaml)
            technical_limits_json = _require_path("technical_limits_json", input_data.technical_limits_json)
            csv_path = Path(load_csv)
            scenario_path = Path(scenario_yaml)
            tl_path = Path(technical_limits_json)
            out_dir = Path(self.results_path or scenario_path.parent)
            out_dir.mkdir(parents=True, exist_ok=True)
            log_path = out_dir / "sizing_optimization.log"

            def _log(msg: str) -> None:
                text = f"[SizingOptimizationPiece] {msg}"
                print(text, flush=True)
                with log_path.open("a", encoding="utf-8") as f:
                    f.write(text + "\n")

            _log(f"Input load_csv={csv_path}")
            _log(f"Input scenario_yaml={scenario_path}")
            _log(f"Input technical_limits_json={tl_path}")
            if not csv_path.is_file():
                raise FileNotFoundError(f"Load CSV not found: {csv_path}")
            if not scenario_path.is_file():
                raise FileNotFoundError(f"Scenario YAML not found: {scenario_path}")
            if not tl_path.is_file():
                raise FileNotFoundError(f"Technical limits JSON not found: {tl_path}")

            try:
                sim = load_simulate_module(caller="SizingOptimizationPiece")
                cfg = yaml.safe_load(scenario_path.read_text(encoding="utf-8")) or {}
                sim._apply_system_scope(cfg)
                df = sim.load_consumption_csv(csv_path)

                eq = cfg.get("equipment") or {}
                mode = str(eq.get("selection_mode", "manual")).lower()
                auto_log = None
                final_cfg = copy.deepcopy(cfg)
                if mode == "auto":
                    _log(f"Running auto sizing on rows={len(df)} (may take a few minutes)")
                    final_cfg, auto_log = sim._auto_optimize_sizes(final_cfg, df)
                _log(f"Resolved selection_mode={mode}, rows={len(df)}")
            except Exception as exc:
                (out_dir / "sizing_optimization_error.txt").write_text(traceback.format_exc(), encoding="utf-8")
                _log(f"ERROR during sizing optimization: {exc}")
                raise

            sized_yaml = out_dir / "scenario_sized.yaml"
            sized_yaml.write_text(
                yaml.safe_dump(final_cfg, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )

            out_json = out_dir / "sizing_optimization.json"
            out_json.write_text(
                json.dumps({"selection_mode": mode, "auto_optimization": auto_log}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            _log(f"Wrote outputs: {sized_yaml}, {out_json}")
            _piece_out = OutputModel(
                message="Sizing optimization finished",
                sized_scenario_yaml=str(sized_yaml),
                sizing_optimization_json=str(out_json),
            )
        finally:
            if od is not None and _piece_out is None:
                od.cleanup_on_error(self.results_path, secrets_data, "SizingOptimizationPiece", _stage)
            elif _stage is not None:
                _stage.cleanup()
        if od is not None and _piece_out is not None:
            return od.finish_piece(_piece_out, self.results_path, secrets_data, "SizingOptimizationPiece", _stage)
        return _piece_out
