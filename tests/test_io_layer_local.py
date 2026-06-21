"""Local (no-credentials) coverage for the optional OneData I/O layer.

The filename deliberately avoids the word that the CI uses for `-k` selection,
so these tests run in the normal job. They prove the additive remote I/O layer
behaves exactly like local pathlib/pandas when no remote secrets/paths are
used, so the existing workflow is never disrupted.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pieces.common import onedata_io as od


def test_has_protocol_only_for_remote_schemes() -> None:
    assert od.has_protocol("onedata:///space/file.csv") is True
    assert od.has_protocol("/home/shared_storage/load.csv") is False
    assert od.has_protocol(r"C:\Users\x\load.csv") is False


def test_configure_credentials_noop_without_secrets() -> None:
    # No secrets and (assuming) no env vars => stays local, returns False.
    assert od.configure_onedata(None) is False
    assert od.configure_onedata({"onedata_token": "", "onedata_onezone_host": ""}) is False


def test_local_csv_roundtrip_via_helper(tmp_path: Path) -> None:
    df = pd.DataFrame({"datetime": ["2025-01-01 00:00:00"], "load_kw": [10.0]})
    target = tmp_path / "sub" / "data.csv"
    od.to_csv(df, str(target), index=False)
    assert od.isfile(str(target)) is True
    back = od.read_csv(str(target))
    assert list(back.columns) == ["datetime", "load_kw"]
    assert float(back.loc[0, "load_kw"]) == 10.0


def test_local_glob_and_move(tmp_path: Path) -> None:
    src_dir = tmp_path / "drop"
    arch_dir = tmp_path / "archive"
    od.makedirs(str(src_dir))
    od.makedirs(str(arch_dir))
    (src_dir / "load_a.csv").write_text("datetime,load_kw\n2025-01-01 00:00:00,1\n", encoding="utf-8")
    (src_dir / "load_b.csv").write_text("datetime,load_kw\n2025-01-01 00:00:00,2\n", encoding="utf-8")

    matches = od.glob(str(src_dir), "load*.csv")
    assert len(matches) == 2

    dst = arch_dir / "load_a.csv"
    od.move(matches[0], str(dst))
    assert od.exists(str(dst)) is True


def test_boundary_pieces_accept_optional_secrets(tmp_path: Path) -> None:
    """FetchEnergyDataPiece runs locally with secrets_data=None (default path)."""
    from pieces.FetchEnergyDataPiece.models import InputModel as FetchInput
    from pieces.FetchEnergyDataPiece.piece import FetchEnergyDataPiece

    load_csv = tmp_path / "load.csv"
    load_csv.write_text(
        "datetime,load_kw\n2025-01-01 00:00:00,10\n2025-01-01 00:15:00,11\n",
        encoding="utf-8",
    )
    results = tmp_path / "out"
    results.mkdir()

    piece = FetchEnergyDataPiece.__new__(FetchEnergyDataPiece)
    piece.results_path = str(results)
    out = piece.piece_function(
        FetchInput(load_csv=str(load_csv), prices_csv=str(tmp_path / "missing_prices.csv")),
        secrets_data=None,
    )
    assert out.output_path
    assert Path(out.output_path).is_file()
