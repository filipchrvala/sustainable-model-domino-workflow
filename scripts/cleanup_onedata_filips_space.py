"""Clean FilipsSpace OneData: keep workflow inputs + empty output folders only."""
from __future__ import annotations

import os
import shutil
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

SPACE = "onedata:///FilipsSpace"
OLD_INPUTS = f"{SPACE}/inputs"
COST_IN = "onedata:///FilipsSpace/cost_optimizer/inputs"
COST_OUT = "onedata:///FilipsSpace/cost_optimizer/outputs"
SUS_IN = DEFAULT_INPUT_DIR
SUS_OUT = DEFAULT_OUTPUT_DIR
SEED_LOCAL = ROOT / "seed_inputs"

SECRETS = {
    "onedata_onezone_host": os.environ.get("ONEDATA_ONEZONE_HOST", DEFAULT_ONEZONE_HOST),
    "onedata_token": os.environ.get("ONEDATA_TOKEN", DEFAULT_ONEDATA_TOKEN),
    "onedata_output_dir": SUS_OUT,
}

KEEP_TOP = {"cost_optimizer", "sustainable_model"}


def _rm_tree(remote: str) -> None:
    if not od.exists(remote):
        return
    if od.isdir(remote):
        for child in od.listdir(remote):
            if od.isdir(child):
                _rm_tree(child)
            else:
                od.remove(child)
    else:
        od.remove(remote)


def _download_tree(remote: str, local: Path) -> None:
    local.mkdir(parents=True, exist_ok=True)
    if od.isfile(remote):
        local.write_bytes(od.read_bytes(remote))
        return
    if not od.isdir(remote):
        return
    for child in od.listdir(remote):
        name = od.normalize_remote_path(child).rsplit("/", 1)[-1]
        dst = local / name
        if od.isdir(child):
            _download_tree(child, dst)
        elif od.isfile(child):
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(od.read_bytes(child))


def _upload_tree(local: Path, remote_prefix: str) -> None:
    for p in sorted(local.rglob("*")):
        if p.is_file():
            rel = p.relative_to(local).as_posix()
            target = f"{remote_prefix.rstrip('/')}/{rel}"
            od.write_bytes(target, p.read_bytes())
            print("  uploaded", target)


def main() -> None:
    od.configure_onedata(SECRETS, force=True)
    print("Backing up old inputs to seed_inputs/ ...")
    if od.exists(OLD_INPUTS):
        if SEED_LOCAL.exists():
            shutil.rmtree(SEED_LOCAL)
        _download_tree(OLD_INPUTS, SEED_LOCAL)
        print("  saved", SEED_LOCAL)

    print("Cleaning FilipsSpace ...")
    for entry in od.listdir(SPACE):
        name = entry.rsplit("/", 1)[-1]
        if name in KEEP_TOP:
            continue
        print("  delete", entry)
        _rm_tree(entry)

    for out_dir in (COST_OUT, SUS_OUT):
        _rm_tree(out_dir)
        od.makedirs(out_dir, exist_ok=True)
        print("  cleared", out_dir)

    _rm_tree(OLD_INPUTS)
    _rm_tree(f"{SPACE}/run")
    for prefix in ("run_test", "run_test_mrk", "run_test_mrk2"):
        _rm_tree(f"{SPACE}/{prefix}")

    od.makedirs(SUS_IN, exist_ok=True)
    print("Seeding sustainable_model/inputs ...")
    if SEED_LOCAL.is_dir():
        _upload_tree(SEED_LOCAL, SUS_IN)
    else:
        print("  WARN: no seed_inputs backup — run scripts/seed_onedata_sustainable_model_inputs.py")

    print("Done. Structure:")
    print(" ", COST_IN, "(unchanged if present)")
    print(" ", SUS_IN)
    print(" ", SUS_OUT, "(empty)")


if __name__ == "__main__":
    main()
