"""
User-edited JSON: tests/user_input/workflow_user_input.json

Orchestrator writes merged YAML only under tests/_generated/ (not under *Piece_Inputs).
"""
from __future__ import annotations

import json
from typing import Any

import yaml
from pydantic import BaseModel, Field

WORKFLOW_USER_INPUT_FORMAT = "workflow_user_input_v1"


class ProjectOptions(BaseModel):
    """High-level toggles applied after TechnicalLimitsPiece."""

    include_solar_pv: bool = Field(default=True, description="If false, max kWp is forced to 0 for sizing.")
    include_battery: bool = Field(default=True, description="If false, max kWh is forced to 0 for sizing.")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, val in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def load_workflow_user_input() -> tuple[ProjectOptions, dict[str, Any], dict[str, Any], dict[str, Any]]:
    """
    Load unified JSON (required for the Alternate workflow).

    Returns:
        project_options, constraints, economics, extras_for_materialize
        extras_for_materialize keys:
        solar_config, investment_eval, scenario, battery_config (dicts merged into _generated YAMLs).
    """
    from workflow import paths as P

    json_path = P.WORKFLOW_USER_INPUT_JSON
    if not json_path.is_file():
        raise FileNotFoundError(
            f"Missing {json_path}. Create tests/user_input/workflow_user_input.json "
            f"(format {WORKFLOW_USER_INPUT_FORMAT!r})."
        )
    data = json.loads(json_path.read_text(encoding="utf-8"))
    fmt = data.get("format")
    if fmt and fmt != WORKFLOW_USER_INPUT_FORMAT:
        raise ValueError(
            f"{json_path} has unsupported format {fmt!r}; expected {WORKFLOW_USER_INPUT_FORMAT!r}"
        )
    po = ProjectOptions(**(data.get("project_options") or {}))
    uip = data.get("UserInputPiece") or {}
    constraints = dict(uip.get("constraints") or {})
    economics = dict(uip.get("economics") or {})
    extras: dict[str, Any] = {}
    solar_block = data.get("SolarSimPiece") or {}
    if isinstance(solar_block.get("solar_config"), dict):
        extras["solar_config"] = solar_block["solar_config"]
    inv_block = data.get("InvestmentEvalPiece")
    if isinstance(inv_block, dict) and inv_block:
        extras["investment_eval"] = inv_block
    batt_piece = data.get("BatterySimPiece") or {}
    if isinstance(batt_piece.get("scenario"), dict):
        extras["scenario"] = batt_piece["scenario"]
    if isinstance(batt_piece.get("battery_config"), dict):
        extras["battery_config"] = batt_piece["battery_config"]
    return po, constraints, economics, extras


def _load_user_scenario_template() -> dict[str, Any]:
    from workflow import paths as P

    if not P.USER_SCENARIO_YML.is_file():
        return {}
    return yaml.safe_load(P.USER_SCENARIO_YML.read_text(encoding="utf-8")) or {}


def materialize_scenario_config(extras: dict[str, Any]) -> None:
    """
    Build tests/_generated/scenario.yml from user template + optional JSON overrides.
    """
    from workflow import paths as P

    P.GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    scenario_path = P.GENERATED_SCENARIO_YML
    base = _load_user_scenario_template()
    if scenario_path.is_file():
        base = _deep_merge(base, yaml.safe_load(scenario_path.read_text(encoding="utf-8")) or {})
    override = extras.get("scenario") if isinstance(extras.get("scenario"), dict) else {}
    merged = _deep_merge(base, override)
    scenario_path.write_text(
        yaml.safe_dump(merged, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def materialize_optional_configs(extras: dict[str, Any]) -> None:
    """
    Merge JSON sections into tests/_generated/*.yml (consumed by pieces after sizing updates).
    """
    from workflow import paths as P

    P.GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    materialize_scenario_config(extras)

    if "solar_config" in extras and extras["solar_config"]:
        base_path = P.GENERATED_SOLAR_CONFIG_YML
        base: dict[str, Any] = {}
        if base_path.is_file():
            base = yaml.safe_load(base_path.read_text(encoding="utf-8")) or {}
        merged = _deep_merge(base, extras["solar_config"])
        base_path.write_text(
            yaml.safe_dump(merged, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )

    if "investment_eval" in extras and extras["investment_eval"]:
        inv_path = P.GENERATED_INVESTMENT_CONFIG_YML
        base = {}
        if inv_path.is_file():
            base = yaml.safe_load(inv_path.read_text(encoding="utf-8")) or {}
        merged = _deep_merge(base, extras["investment_eval"])
        inv_path.write_text(
            yaml.safe_dump(merged, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )

    if "battery_config" in extras and extras["battery_config"]:
        batt_path = P.GENERATED_BATTERY_CONFIG_YML
        base_b = {}
        if batt_path.is_file():
            base_b = yaml.safe_load(batt_path.read_text(encoding="utf-8")) or {}
        merged_b = _deep_merge(base_b, extras["battery_config"])
        batt_path.write_text(
            yaml.safe_dump(merged_b, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
