"""Write piece diagnostics to results_path before OneData staging (Domino Logs tab)."""
from __future__ import annotations

from pathlib import Path


def bootstrap_log(results_path: str | None, piece_name: str, msg: str) -> Path | None:
    text = f"[{piece_name}] {msg}"
    print(text, flush=True)
    if not results_path:
        return None
    out_dir = Path(results_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / f"{piece_name.lower()}_bootstrap.log"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(text + "\n")
    return log_path
