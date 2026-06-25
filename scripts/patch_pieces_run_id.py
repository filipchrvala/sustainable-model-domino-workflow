"""Add run_id propagation to OneData-wrapped pieces."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = {"FetchEnergyDataPiece", "UserInputPiece"}


def patch_piece(path: Path) -> None:
    name = path.parent.name
    text = path.read_text(encoding="utf-8")
    if "stage_inputs" not in text:
        return
    orig = text

    if "_run_id" not in text:
        text = text.replace(
            "        _piece_out = None\n        if od is not None:\n"
            "            input_data, _stage = od.stage_inputs(input_data, secrets_data)",
            "        _piece_out = None\n        _run_id = None\n        if od is not None:\n"
            "            input_data, _stage = od.stage_inputs(input_data, secrets_data)\n"
            f"            _run_id = od.resolve_run_id(input_data, secrets_data, generate={name in ENTRY})",
        )
        text = text.replace(
            "        _stage = None\n        if od is not None:\n"
            "            input_data, _stage = od.stage_inputs(input_data, secrets_data)\n"
            "        _piece_out = None",
            "        _stage = None\n        _piece_out = None\n        _run_id = None\n"
            "        if od is not None:\n"
            "            input_data, _stage = od.stage_inputs(input_data, secrets_data)\n"
            f"            _run_id = od.resolve_run_id(input_data, secrets_data, generate={name in ENTRY})",
        )

    text = re.sub(
        r'od\.cleanup_on_error\(([^)]+)\)',
        lambda m: m.group(0) if "run_id=" in m.group(0) else m.group(0)[:-1] + ", run_id=_run_id)",
        text,
    )
    text = re.sub(
        r'od\.finish_piece\(([^)]+)\)',
        lambda m: m.group(0) if "run_id=" in m.group(0) else m.group(0)[:-1] + ", run_id=_run_id)",
        text,
    )

    if name in ENTRY and "_run_id" in text:
        # Ensure output carries run_id when model has the field
        text = re.sub(
            r"(_piece_out = OutputModel\([^)]*)\)",
            lambda m: m.group(1) + (", run_id=_run_id or \"\"" if "run_id=" not in m.group(0) else "") + ")",
            text,
            count=1,
        )

    if text != orig:
        path.write_text(text, encoding="utf-8")
        print("patched", name)


def main() -> None:
    for piece in sorted((ROOT / "pieces").glob("*/piece.py")):
        patch_piece(piece)


if __name__ == "__main__":
    main()
