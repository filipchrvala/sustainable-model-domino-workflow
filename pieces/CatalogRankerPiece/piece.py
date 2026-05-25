from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys
import traceback

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


class CatalogRankerPiece(BasePiece):
    """Produce top ranked online PV modules for current scenario."""

    def piece_function(self, input_data: InputModel) -> OutputModel:
        scenario_path = Path(input_data.scenario_yaml)
        pv_path = Path(input_data.pv_catalog_json)
        out_dir = Path(self.results_path or scenario_path.parent)
        out_dir.mkdir(parents=True, exist_ok=True)
        log_path = out_dir / "catalog_ranker.log"

        def _log(msg: str) -> None:
            text = f"[CatalogRankerPiece] {msg}"
            print(text, flush=True)
            with log_path.open("a", encoding="utf-8") as f:
                f.write(text + "\n")

        _log(f"Input scenario_yaml={scenario_path}")
        _log(f"Input pv_catalog_json={pv_path}")
        if not scenario_path.is_file():
            raise FileNotFoundError(f"Scenario YAML not found: {scenario_path}")
        if not pv_path.is_file():
            raise FileNotFoundError(f"PV catalog JSON not found: {pv_path}")

        try:
            sim = _load_simulate_module()
            cfg = yaml.safe_load(scenario_path.read_text(encoding="utf-8")) or {}
            inst = ((cfg.get("equipment") or {}).get("constraints") or {}).get("installation") or {}
            installed_kwp = float((cfg.get("pv") or {}).get("installed_kwp", 0.0))
            items = (json.loads(pv_path.read_text(encoding="utf-8")) or {}).get("items") or []
            ranked = sim.rank_pv_modules_for_site(items, installation=inst)
            top = []
            for r in ranked[:10]:
                m = r["module"]
                wp = float(m.get("stc_watts", 0) or 0)
                n_mod = int((installed_kwp * 1000.0 + wp - 1) // max(wp, 1.0)) if wp > 0 else 0
                top.append(
                    {
                        "manufacturer": m.get("manufacturer"),
                        "model": m.get("model"),
                        "power_wp": wp,
                        "score": r["score"],
                        "module_count_estimate": n_mod,
                    }
                )
            _log(f"Ranked {len(items)} modules, top_count={len(top)}")
        except Exception as exc:
            (out_dir / "catalog_ranker_error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            _log(f"ERROR during catalog ranking: {exc}")
            raise

        out_json = out_dir / "catalog_ranked_recommendation.json"
        out_json.write_text(
            json.dumps(
                {"installed_kwp_target": installed_kwp, "top_recommendations": top},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        _log(f"Wrote output: {out_json}")
        return OutputModel(message="Catalog ranking finished", catalog_ranked_recommendation_json=str(out_json))
