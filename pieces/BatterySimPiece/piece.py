from __future__ import annotations

import importlib
from pathlib import Path
import sys
import traceback

import pandas as pd
import yaml
try:
    from domino.base_piece import BasePiece
except ModuleNotFoundError:
    from local_compat.base_piece import BasePiece

from .models import InputModel, OutputModel


def _load_simulate_module():
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return importlib.import_module("pieces.SimulatePiece.piece")


class BatterySimPiece(BasePiece):
    """Generate battery SOC profile using dispatch model."""

    def piece_function(self, input_data: InputModel) -> OutputModel:
        csv_path = Path(input_data.load_csv)
        scenario_path = Path(input_data.scenario_yaml)
        solar_path = Path(input_data.virtual_solar_csv)
        out_dir = Path(self.results_path or scenario_path.parent)
        out_dir.mkdir(parents=True, exist_ok=True)
        log_path = out_dir / "battery_sim.log"

        def _log(msg: str) -> None:
            text = f"[BatterySimPiece] {msg}"
            print(text, flush=True)
            with log_path.open("a", encoding="utf-8") as f:
                f.write(text + "\n")

        _log(f"Input load_csv={csv_path}")
        _log(f"Input scenario_yaml={scenario_path}")
        _log(f"Input virtual_solar_csv={solar_path}")
        if not csv_path.is_file():
            raise FileNotFoundError(f"Load CSV not found: {csv_path}")
        if not scenario_path.is_file():
            raise FileNotFoundError(f"Scenario YAML not found: {scenario_path}")
        if not solar_path.is_file():
            raise FileNotFoundError(f"Virtual solar CSV not found: {solar_path}")

        try:
            sim = _load_simulate_module()
            cfg = yaml.safe_load(scenario_path.read_text(encoding="utf-8")) or {}
            df = sim.load_consumption_csv(csv_path)
            solar_df = pd.read_csv(solar_path)
            if "pv_kw" not in solar_df.columns:
                raise ValueError("virtual_solar_csv must contain pv_kw column")

            dt_h = sim.infer_timestep_hours(df)
            price = sim.build_price_series(df, cfg).values.astype(float)
            net = df["load_kw"].astype(float).values - solar_df["pv_kw"].astype(float).values

            bat = cfg.get("battery") or {}
            mrk = cfg.get("mrk") or {}
            en = cfg.get("energy") or {}
            _g, soc, _pb, _exp = sim.dispatch_battery(
                net_load_kw=net,
                price=price,
                dt_h=dt_h,
                energy_kwh=float(bat.get("energy_kwh", 0.0)),
                max_c_rate=float(bat.get("max_c_rate", 0.5)),
                eta_c=float(bat.get("charge_efficiency", 0.95)),
                eta_d=float(bat.get("discharge_efficiency", 0.95)),
                initial_soc_pct=float(bat.get("initial_soc_pct", 50.0)),
                mrk_contract_kw=float(mrk.get("contract_kw", 0.0)),
                feed_in_eur_per_kwh=float(en.get("feed_in_surplus_eur_per_kwh", 0.05)),
                pv_lcoe_eur_per_kwh=0.12,
                battery_throughput_eur_per_kwh=0.02,
                max_fraction_from_grid_charge=float(bat.get("max_fraction_capacity_from_grid_charge", 0.72)),
            )
            out_df = pd.DataFrame({"datetime": df["datetime"], "soc_pct": soc})
            cycles = float(sim.equivalent_full_cycles(pd.Series(soc)))
            throughput_mwh = float(
                (pd.Series(soc).diff().abs().fillna(0.0).sum() / 100.0) * float(bat.get("energy_kwh", 0.0)) / 1000.0
            )
            summary_df = pd.DataFrame(
                [
                    {
                        "capacity_kWh": float(bat.get("energy_kwh", 0.0)),
                        "cycles_equivalent": round(cycles, 4),
                        "energy_throughput_MWh": round(throughput_mwh, 4),
                    }
                ]
            )
            _log(f"Computed battery SOC rows={len(out_df)}")
        except Exception as exc:
            (out_dir / "battery_sim_error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            _log(f"ERROR during battery simulation: {exc}")
            raise

        out_csv = out_dir / "virtual_battery_soc.csv"
        summary_csv = out_dir / "battery_summary.csv"
        out_df.to_csv(out_csv, index=False)
        summary_df.to_csv(summary_csv, index=False)
        _log(f"Wrote outputs: {out_csv}, {summary_csv}")
        return OutputModel(
            message="Battery simulation finished",
            virtual_battery_soc_csv=str(out_csv),
            battery_summary_csv=str(summary_csv),
        )
