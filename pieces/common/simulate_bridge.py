"""Lazy import bridge for MRK helpers in SimulatePiece.piece."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path


def load_simulate_module(*, caller: str = "piece") -> object:
    repo_root = Path(__file__).resolve().parents[1].parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    print(f"[INFO] {caller}: loading MRK simulation module", flush=True)
    return importlib.import_module("pieces.SimulatePiece.piece")
