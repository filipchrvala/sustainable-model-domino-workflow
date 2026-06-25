"""Upload UC3.3 workflow seed inputs to OneData (sustainable_model/inputs/)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pieces"))

from common import onedata_io as od  # noqa: E402
from common.onedata_defaults import (  # noqa: E402
    DEFAULT_INPUT_DIR,
    DEFAULT_ONEDATA_TOKEN,
    DEFAULT_ONEZONE_HOST,
    DEFAULT_OUTPUT_DIR,
)

SEED = ROOT / "seed_inputs"
DOMINO_DATA = Path(os.environ.get("DOMINO_DATA", r"c:\Users\NTB\domino_data"))
INDUSTRIAL = DOMINO_DATA / "sustainable_model_industrial"

SECRETS = {
    "onedata_onezone_host": os.environ.get("ONEDATA_ONEZONE_HOST", DEFAULT_ONEZONE_HOST),
    "onedata_token": os.environ.get("ONEDATA_TOKEN", DEFAULT_ONEDATA_TOKEN),
    "onedata_output_dir": os.environ.get("ONEDATA_OUTPUT_DIR", DEFAULT_OUTPUT_DIR),
}

# Remote paths relative to DEFAULT_INPUT_DIR
REMOTE_FILES = [
    "load.csv",
    "prices.csv",
    "scenario.yaml",
    "workflow_user_input.json",
    "web_form_state.json",
    "predict_planned_load_halfyear.csv",
    "sustainable/history/energy_history.csv",
]

GITHUB_ONEDATA_BRANCH = "github-onedata"


def _extract_from_git(rel: str, dst: Path) -> bool:
    try:
        data = subprocess.check_output(
            ["git", "-C", str(ROOT), "show", f"{GITHUB_ONEDATA_BRANCH}:tests/{rel}"],
        )
    except subprocess.CalledProcessError:
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    return True


def _ensure_seed_files() -> None:
    SEED.mkdir(parents=True, exist_ok=True)
    mapping = {
        "load.csv": ("FetchEnergyDataPiece_Inputs/load_seed.csv", INDUSTRIAL / "load.csv"),
        "prices.csv": ("FetchEnergyDataPiece_Inputs/prices.csv", INDUSTRIAL / "prices.csv"),
        "scenario.yaml": ("user_input/scenario.yaml", INDUSTRIAL / "scenario.yaml"),
        "workflow_user_input.json": ("user_input/workflow_user_input.json", DOMINO_DATA / "sustainable_model" / "workflow_user_input.json"),
        "web_form_state.json": ("WebUserInputPiece_Input/web_form_state.json", None),
        "predict_planned_load_halfyear.csv": ("PredictPiece_Inputs/predict_planned_load_halfyear.csv", None),
        "sustainable/history/energy_history.csv": ("sustainable/history/energy_history.csv", None),
    }
    for remote_name, (git_rel, fallback) in mapping.items():
        dst = SEED / remote_name
        if dst.is_file():
            continue
        if fallback and Path(fallback).is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(Path(fallback).read_bytes())
            print("copied local", fallback, "->", dst)
        elif _extract_from_git(git_rel, dst):
            print("extracted git", git_rel, "->", dst)

    for sub in ("sustainable/company_drop", "sustainable/company_archive", "sustainable/model_registry"):
        local = SEED / sub
        if local.is_dir() and any(local.iterdir()):
            continue
        git_prefix = f"{sub.replace('sustainable/', 'sustainable/')}"
        try:
            out = subprocess.check_output(
                ["git", "-C", str(ROOT), "ls-tree", "-r", "--name-only", GITHUB_ONEDATA_BRANCH, f"tests/{git_prefix}"],
                text=True,
            )
        except subprocess.CalledProcessError:
            continue
        for line in out.strip().splitlines():
            if not line:
                continue
            rel = line.split("tests/", 1)[-1]
            _extract_from_git(rel, SEED / rel.split("tests/", 1)[-1].replace("tests/", ""))


def main() -> None:
    _ensure_seed_files()
    od.configure_onedata(SECRETS, force=True)
    prefix = DEFAULT_INPUT_DIR.rstrip("/")
    print(f"Uploading to {prefix}/\n")
    for remote_name in REMOTE_FILES:
        src = SEED / remote_name
        if not src.is_file():
            print("SKIP missing", src)
            continue
        target = f"{prefix}/{remote_name}"
        od.write_bytes(target, src.read_bytes())
        print("uploaded", target)
    for sub in ("sustainable/company_drop", "sustainable/company_archive", "sustainable/model_registry"):
        local = SEED / sub
        if not local.is_dir():
            continue
        for p in sorted(local.rglob("*")):
            if p.is_file():
                rel = p.relative_to(SEED).as_posix()
                target = f"{prefix}/{rel}"
                od.write_bytes(target, p.read_bytes())
                print("uploaded", target)
    print("Inputs ready under", DEFAULT_INPUT_DIR)


if __name__ == "__main__":
    main()
