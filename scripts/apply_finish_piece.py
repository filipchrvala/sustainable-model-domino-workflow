"""One-shot codemod: wire finish_piece / cleanup_on_error into all piece.py files."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIECES = ROOT / "pieces"

FINALLY_RE = re.compile(
    r"(\s+)finally:\n"
    r"\1    if od is not None:\n"
    r"(?:\1        od\.upload_registry\(_reg_local, _reg_target\)\n)?"
    r"\1        od\.mirror_results\(self\.results_path, secrets_data, \"([^\"]+)\"\)\n"
    r"\1    if _stage is not None:\n"
    r"\1        _stage\.cleanup\(\)\n",
    re.MULTILINE,
)

REGISTRY_FINALLY = re.compile(
    r"(\s+)finally:\n"
    r"\1    if od is not None:\n"
    r"\1        od\.upload_registry\(_reg_local, _reg_target\)\n"
    r"\1        od\.mirror_results\(self\.results_path, secrets_data, \"([^\"]+)\"\)\n"
    r"\1    if _stage is not None:\n"
    r"\1        _stage\.cleanup\(\)\n",
    re.MULTILINE,
)


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if "finish_piece" in text or "mirror_results" not in text:
        return False

    m = FINALLY_RE.search(text)
    if not m:
        print(f"SKIP (no finally): {path.relative_to(ROOT)}")
        return False
    indent, piece_name = m.group(1), m.group(2)
    has_registry = "upload_registry" in m.group(0)

    if "_piece_out = None" not in text:
        text = text.replace(
            "input_data, _stage = od.stage_inputs(input_data, secrets_data)",
            "input_data, _stage = od.stage_inputs(input_data, secrets_data)\n        _piece_out = None",
            1,
        )
        if "_piece_out = None" not in text:
            # SustainableIngest / Fetch may not use stage_inputs at start
            text = text.replace(
                "def piece_function(self, input_data: InputModel, secrets_data=None) -> OutputModel:",
                "def piece_function(self, input_data: InputModel, secrets_data=None) -> OutputModel:\n        _piece_out = None",
                1,
            )

    text = re.sub(r"\breturn OutputModel\(", "_piece_out = OutputModel(", text)

    if has_registry:
        new_finally = (
            f"{indent}finally:\n"
            f"{indent}    if od is not None and _piece_out is None:\n"
            f"{indent}        od.cleanup_on_error(\n"
            f"{indent}            self.results_path, secrets_data, \"{piece_name}\", _stage,\n"
            f"{indent}            registry_local=_reg_local, registry_target=_reg_target,\n"
            f"{indent}        )\n"
            f"{indent}    elif _stage is not None:\n"
            f"{indent}        _stage.cleanup()\n"
            f"{indent}if od is not None and _piece_out is not None:\n"
            f"{indent}    return od.finish_piece(\n"
            f"{indent}        _piece_out, self.results_path, secrets_data, \"{piece_name}\", _stage,\n"
            f"{indent}        registry_local=_reg_local, registry_target=_reg_target,\n"
            f"{indent}    )\n"
            f"{indent}return _piece_out\n"
        )
        text = REGISTRY_FINALLY.sub(new_finally, text, count=1)
    else:
        new_finally = (
            f"{indent}finally:\n"
            f"{indent}    if od is not None and _piece_out is None:\n"
            f"{indent}        od.cleanup_on_error(self.results_path, secrets_data, \"{piece_name}\", _stage)\n"
            f"{indent}    elif _stage is not None:\n"
            f"{indent}        _stage.cleanup()\n"
            f"{indent}if od is not None and _piece_out is not None:\n"
            f"{indent}    return od.finish_piece(_piece_out, self.results_path, secrets_data, \"{piece_name}\", _stage)\n"
            f"{indent}return _piece_out\n"
        )
        text = FINALLY_RE.sub(new_finally, text, count=1)

    path.write_text(text, encoding="utf-8")
    print(f"PATCHED: {path.relative_to(ROOT)}")
    return True


def main() -> None:
    n = 0
    for path in sorted(PIECES.glob("*/piece.py")):
        if patch_file(path):
            n += 1
    print(f"\nDone: {n} file(s) patched.")


if __name__ == "__main__":
    main()
