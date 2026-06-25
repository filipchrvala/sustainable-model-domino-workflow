from __future__ import annotations

from pathlib import Path
import traceback

import pandas as pd
import yaml
try:
    from domino.base_piece import BasePiece
except ModuleNotFoundError:
    from local_compat.base_piece import BasePiece

from .models import InputModel, OutputModel

print("[INFO] SolarSimPiece module loaded", flush=True)

try:
    from common import mrk_helpers as mrk
    from common import piece_bootstrap as boot
except ModuleNotFoundError:
    from pieces.common import mrk_helpers as mrk
    from pieces.common import piece_bootstrap as boot

try:
    from common import onedata_io as od
except ModuleNotFoundError:
    try:
        from pieces.common import onedata_io as od
    except ModuleNotFoundError:
        od = None


class SolarSimPiece(BasePiece):
    """Create virtual PV production CSV from selected scenario."""

    def piece_function(self, input_data: InputModel, secrets_data=None) -> OutputModel:
        boot.bootstrap_log(self.results_path, "SolarSimPiece", "piece_function started")
        boot.bootstrap_log(
            self.results_path,
            "SolarSimPiece",
            f"inputs load_csv={input_data.load_csv!r} scenario_yaml={input_data.scenario_yaml!r}",
        )
        _stage = None
        if od is not None:
            try:
                input_data, _stage = od.stage_inputs(input_data, secrets_data)
            except Exception as exc:
                boot.bootstrap_log(self.results_path, "SolarSimPiece", f"stage_inputs FAILED: {exc}")
                if od is not None:
                    od.cleanup_on_error(self.results_path, secrets_data, "SolarSimPiece", _stage, run_id=_run_id)
                raise
        _piece_out = None
        try:
            csv_path = Path(input_data.load_csv)
            scenario_path = Path(input_data.scenario_yaml)
            out_dir = Path(self.results_path or scenario_path.parent)
            out_dir.mkdir(parents=True, exist_ok=True)
            log_path = out_dir / "solar_sim.log"

            def _log(msg: str) -> None:
                text = f"[SolarSimPiece] {msg}"
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
                cfg = yaml.safe_load(scenario_path.read_text(encoding="utf-8")) or {}
                pv = cfg.get("pv") or {}
                installed_kwp = float(pv.get("installed_kwp", 0.0))
                yield_kwp = float(pv.get("yield_kwh_per_kwp_year", 1000.0))
                df = mrk.load_consumption_csv(csv_path)
                pv_kw = mrk.synthetic_pv_kw(df["datetime"], installed_kwp, yield_kwh_per_kwp_year=yield_kwp)
                out_df = pd.DataFrame({"datetime": df["datetime"], "pv_kw": pv_kw})
                _log(f"Computed virtual solar rows={len(out_df)}, installed_kwp={installed_kwp}")
            except Exception as exc:
                (out_dir / "solar_sim_error.txt").write_text(traceback.format_exc(), encoding="utf-8")
                _log(f"ERROR during solar simulation: {exc}")
                raise

            out_csv = out_dir / "virtual_solar.csv"
            out_df.to_csv(out_csv, index=False)
            _log(f"Wrote output: {out_csv}")
            _piece_out = OutputModel(message="Solar simulation finished", virtual_solar_csv=str(out_csv))
        finally:
            if od is not None and _piece_out is None:
                od.cleanup_on_error(self.results_path, secrets_data, "SolarSimPiece", _stage, run_id=_run_id)
            elif _stage is not None:
                _stage.cleanup()
        if od is not None and _piece_out is not None:
            return od.finish_piece(_piece_out, self.results_path, secrets_data, "SolarSimPiece", _stage, run_id=_run_id)
        return _piece_out
