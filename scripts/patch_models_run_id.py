"""Add RunIdInputMixin and OneDataSecretsModel to all piece models."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIECES = ROOT / "pieces"

IMPORT_BLOCK = """try:
    from common.onedata_models import OneDataSecretsModel, RunIdInputMixin
except ModuleNotFoundError:
    from pieces.common.onedata_models import OneDataSecretsModel, RunIdInputMixin
"""

ENTRY_OUTPUT_PIECES = {"FetchEnergyDataPiece", "UserInputPiece"}

SECRETS_RE = re.compile(
    r"class SecretsModel\(BaseModel\):\s*\n(?:.*?\n)*?(?=\n\nclass |\nclass OutputModel|\Z)",
    re.MULTILINE,
)


def _patch_file(path: Path, piece_name: str) -> None:
    text = path.read_text(encoding="utf-8")
    orig = text

    if "RunIdInputMixin" not in text:
        if "from pydantic import" in text:
            text = text.replace(
                "from pydantic import",
                IMPORT_BLOCK + "\n\nfrom pydantic import",
                1,
            )
        else:
            text = IMPORT_BLOCK + "\n\n" + text

    text = re.sub(
        r"class InputModel\(BaseModel\):",
        "class InputModel(RunIdInputMixin):",
        text,
        count=1,
    )

    if "class SecretsModel(BaseModel):" in text:
        text = SECRETS_RE.sub("class SecretsModel(OneDataSecretsModel):\n    pass\n\n", text)

    if piece_name in ENTRY_OUTPUT_PIECES and "run_id:" not in text.split("class OutputModel", 1)[-1]:
        text = re.sub(
            r"(class OutputModel\(BaseModel\):\s*\n(?:[^\n]*\n)*?)(\n)",
            r'\1    run_id: str = Field(default="", description="Workflow run id for OneData output subfolder")\n\2',
            text,
            count=1,
        )
        if "Field" not in text.split("class OutputModel")[0]:
            text = text.replace("from pydantic import BaseModel", "from pydantic import BaseModel, Field", 1)

    if text != orig:
        path.write_text(text, encoding="utf-8")
        print("patched", path.relative_to(ROOT))


def main() -> None:
    for models in sorted(PIECES.glob("*/models.py")):
        _patch_file(models, models.parent.name)


if __name__ == "__main__":
    main()
