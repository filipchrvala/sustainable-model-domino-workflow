"""Export Domino-importable workflow JSON from sus_onedata.customization."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CUSTOM = ROOT / "sus_onedata.customization"
CONFIG = ROOT / "config.toml"
OUT_GHCR = ROOT / "sus_onedata.json"
OUT_SPICE = ROOT / "sus_onedata.spice.json"
WORKFLOWS_PACK = (
    Path(__file__).resolve().parents[2]
    / "uc3-domino-gitlab-sync"
    / "sustainable_model_onedata"
    / "UC3.3_sustainable_model_onedata.json"
)


def _version() -> str:
    text = CONFIG.read_text(encoding="utf-8") if CONFIG.is_file() else ""
    match = re.search(r'VERSION\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else "0.1.33"


def _image(*, spice: bool, version: str) -> str:
    if spice:
        return (
            f"harbor.testbed.spice-platform.eu/partner/uc3/"
            f"industry_sg_vre_sustainable_model:{version}-group0"
        )
    return f"ghcr.io/filipchrvala/sustainable-model-domino-workflow:{version}-group0"


def _repo_urls(*, spice: bool) -> tuple[str, str]:
    if spice:
        base = "https://gitlab.spice-platform.eu/use-cases/uc3/UC3.3_Industry_Sg_Vre_Sustainable_Model"
    else:
        base = "https://github.com/filipchrvala/sustainable-model-domino-workflow"
    return base, base


def export(*, spice: bool) -> dict:
    data = json.loads(CUSTOM.read_text(encoding="utf-8"))
    version = _version()
    image = _image(spice=spice, version=version)
    repo_url, repo_base = _repo_urls(spice=spice)
    for piece in data.get("workflowPieces", {}).values():
        piece["source_image"] = image
        piece["repository_url"] = repo_url
        name = piece.get("name", "")
        if name:
            piece["source_url"] = f"{repo_base}/tree/main/pieces/{name}"
    return data


def write(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Wrote {path} ({path.stat().st_size} bytes)")


def main() -> int:
    ghcr = export(spice=False)
    write(OUT_GHCR, ghcr)

    spice = export(spice=True)
    write(OUT_SPICE, spice)
    if WORKFLOWS_PACK.parent.is_dir():
        write(WORKFLOWS_PACK, spice)
    else:
        print(f"Skip workflows pack (missing {WORKFLOWS_PACK.parent})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
