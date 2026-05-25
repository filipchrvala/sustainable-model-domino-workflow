from __future__ import annotations

import logging
from pathlib import Path
from typing import Any


class BasePiece:
    """Minimal local fallback when Domino runtime is unavailable."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.results_path = kwargs.get("results_path", "")
        self.deploy_mode = kwargs.get("deploy_mode", "local")
        self.task_id = kwargs.get("task_id", "local-task")
        self.dag_id = kwargs.get("dag_id", "local-dag")
        self.logger = kwargs.get("logger", logging.getLogger(self.__class__.__name__))
        self.display_result = kwargs.get("display_result")

    def ensure_results_path(self) -> Path:
        path = Path(self.results_path or '.')
        path.mkdir(parents=True, exist_ok=True)
        self.results_path = str(path)
        return path
