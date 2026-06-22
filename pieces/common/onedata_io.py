"""Optional OneData (fsspec) I/O layer for boundary pieces.

Design goals (do NOT break the existing local/Domino workflow):

* When no OneData secret is configured AND the path is a plain local path,
  every helper behaves exactly like the current ``pathlib`` / ``pandas`` code.
* When OneData secrets are configured AND the path carries a protocol
  (e.g. ``onedata:///space/file.csv``), the same helper transparently routes
  through ``fsspec`` + the ``onedatarestfsspec`` backend.
* ``fsspec`` is imported lazily, so a local run without the OneData backend
  installed still works as long as only local paths are used.

Secrets are passed to a piece by Domino as ``secrets_data`` and locally as
``None`` (the orchestrator never sets them), which keeps the local path active.
"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from typing import Any

import pandas as pd

# Protocols we treat as "remote" (handled by fsspec). A plain Windows path
# like ``C:\...`` is NOT a protocol here: ``url_to_fs`` would misread the
# drive letter, so we explicitly only route known remote schemes.
_REMOTE_PROTOCOLS = ("onedata://",)


def has_protocol(path: str | os.PathLike[str]) -> bool:
    """True only for paths that should be handled by fsspec (e.g. onedata://)."""
    text = str(path)
    return text.startswith(_REMOTE_PROTOCOLS)


_backend_ready = False


def _ensure_backend() -> None:
    """Import the vendored onedata fsspec backend so the ``onedata`` protocol is
    registered with fsspec.

    The backend (``onedatarestfsspec``) is vendored next to this module under
    ``common/onedatarestfsspec`` because it is git-only (not on PyPI) and the
    Domino base image has no git to build it. Importing it runs
    ``register_implementation('onedata', ...)`` at module load. Idempotent.
    """
    global _backend_ready
    if _backend_ready:
        return
    try:
        from . import onedatarestfsspec  # noqa: F401  (vendored, self-registers)
    except Exception:
        import sys
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        import onedatarestfsspec  # noqa: F401
    _backend_ready = True


def configure_onedata(secrets_data: Any) -> bool:
    """Register OneData credentials and the backend if both are present.

    Accepts a pydantic model, a dict, or ``None``. Returns ``True`` when the
    OneData backend was configured, ``False`` otherwise (local-only run).
    Falls back to environment variables (used by the onedata pytest jobs).
    """
    host = _get(secrets_data, "onedata_onezone_host") or os.environ.get("ONEDATA_ONEZONE_HOST")
    token = _get(secrets_data, "onedata_token") or os.environ.get("ONEDATA_TOKEN")
    if not host or not token:
        return False

    # The vendored backend reads credentials from these env vars
    # (see onedatarestfsspec.config.get_onedata_config_from_env), so set them
    # before any onedata:// filesystem is created.
    os.environ["ONEDATA_ONEZONE_HOST"] = str(host)
    os.environ["ONEDATA_TOKEN"] = str(token)

    _ensure_backend()
    return True


def _get(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _fs(path: str):
    import fsspec

    _ensure_backend()
    filesystem, fs_path = fsspec.core.url_to_fs(path)
    return filesystem, fs_path


# --- existence / listing -------------------------------------------------

def exists(path: str | os.PathLike[str]) -> bool:
    if has_protocol(path):
        fs, p = _fs(str(path))
        return fs.exists(p)
    return Path(path).exists()


def isfile(path: str | os.PathLike[str]) -> bool:
    if has_protocol(path):
        fs, p = _fs(str(path))
        return fs.isfile(p)
    return Path(path).is_file()


def isdir(path: str | os.PathLike[str]) -> bool:
    if has_protocol(path):
        fs, p = _fs(str(path))
        return fs.isdir(p)
    return Path(path).is_dir()


def glob(directory: str | os.PathLike[str], pattern: str) -> list[str]:
    """List entries matching ``pattern`` inside ``directory``.

    Returns full paths (URLs for remote). Sorted for deterministic order,
    mirroring the existing ``sorted(Path(dir).glob(pattern))`` usage.
    """
    if has_protocol(directory):
        import fsspec

        proto, _ = fsspec.core.split_protocol(str(directory))
        fs, p = _fs(str(directory))
        matches = fs.glob(f"{p.rstrip('/')}/{pattern}")
        return sorted(f"{proto}:///{m.lstrip('/')}" for m in matches)
    return sorted(str(p) for p in Path(directory).glob(pattern))


def makedirs(path: str | os.PathLike[str], exist_ok: bool = True) -> None:
    if has_protocol(path):
        fs, p = _fs(str(path))
        fs.makedirs(p, exist_ok=exist_ok)
        return
    Path(path).mkdir(parents=True, exist_ok=exist_ok)


def ensure_parent_dir(path: str | os.PathLike[str]) -> None:
    if has_protocol(path):
        import fsspec

        fs, p = _fs(str(path))
        parent = str(PurePosixPath(p).parent)
        if parent not in ("", ".", "/"):
            fs.makedirs(parent, exist_ok=True)
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def move(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
    """Move/rename a file. Both paths must be on the same filesystem family."""
    if has_protocol(src) or has_protocol(dst):
        import fsspec

        fs, src_p = _fs(str(src))
        _, dst_p = fsspec.core.url_to_fs(str(dst))
        ensure_parent_dir(dst)
        fs.mv(src_p, dst_p)
        return
    Path(src).rename(dst)


# --- text / bytes --------------------------------------------------------

def read_text(path: str | os.PathLike[str], encoding: str = "utf-8") -> str:
    if has_protocol(path):
        import fsspec

        with fsspec.open(str(path), "r", encoding=encoding) as f:
            return f.read()
    return Path(path).read_text(encoding=encoding)


def write_text(path: str | os.PathLike[str], text: str, encoding: str = "utf-8") -> None:
    if has_protocol(path):
        import fsspec

        ensure_parent_dir(path)
        with fsspec.open(str(path), "w", encoding=encoding) as f:
            f.write(text)
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding=encoding)


# --- pandas IO -----------------------------------------------------------
# pandas natively routes URLs through fsspec once the onedata backend is
# configured, so these thin wrappers work for both local and remote paths.

def read_csv(path: str | os.PathLike[str], **kwargs) -> pd.DataFrame:
    return pd.read_csv(str(path), **kwargs)


def read_parquet(path: str | os.PathLike[str], **kwargs) -> pd.DataFrame:
    return pd.read_parquet(str(path), **kwargs)


def to_csv(df: pd.DataFrame, path: str | os.PathLike[str], **kwargs) -> None:
    if not has_protocol(path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    else:
        ensure_parent_dir(path)
    df.to_csv(str(path), **kwargs)


def to_parquet(df: pd.DataFrame, path: str | os.PathLike[str], **kwargs) -> None:
    if not has_protocol(path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    else:
        ensure_parent_dir(path)
    df.to_parquet(str(path), **kwargs)
