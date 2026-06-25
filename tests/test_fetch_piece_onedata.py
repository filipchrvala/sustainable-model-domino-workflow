"""OneData round-trip test for FetchEnergyDataPiece.

Selected by `pytest -k onedata`. Skipped automatically unless OneData
credentials are provided via env vars (ONEDATA_ONEZONE_HOST + ONEDATA_TOKEN),
so it is safe to collect in any environment.

CI provides the credentials in the dedicated onedata pytest step:
    ONEDATA_ONEZONE_HOST="data.spice-platform.eu" ONEDATA_TOKEN="$ONEDATA_ACCESS_TOKEN"

The OneData space used for scratch files defaults to "DominoPiecesTestSpace"
and can be overridden with ONEDATA_TEST_SPACE.
"""
from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_HOST = os.environ.get("ONEDATA_ONEZONE_HOST")
_TOKEN = os.environ.get("ONEDATA_TOKEN")

pytestmark = pytest.mark.skipif(
    not (_HOST and _TOKEN),
    reason="OneData credentials (ONEDATA_ONEZONE_HOST + ONEDATA_TOKEN) not set",
)


def _space() -> str:
    return os.environ.get("ONEDATA_TEST_SPACE", "DominoPiecesTestSpace")


def test_fetch_energy_data_reads_from_onedata(tmp_path: Path) -> None:
    from pieces.common import onedata_io as od
    from pieces.FetchEnergyDataPiece.models import InputModel as FetchInput, SecretsModel
    from pieces.FetchEnergyDataPiece.piece import FetchEnergyDataPiece

    secrets = SecretsModel(onedata_onezone_host=_HOST, onedata_token=_TOKEN)
    assert od.configure_onedata(secrets) is True

    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    base = f"onedata:///{_space()}/uc33_fetch_test/{stamp}"
    load_url = f"{base}/load.csv"

    df = pd.DataFrame(
        {
            "datetime": ["01.01.25 00:00", "01.01.25 00:15", "01.01.25 00:30"],
            "load_kw": [10.0, 11.0, 12.0],
        }
    )
    od.to_csv(df, load_url, index=False)
    assert od.isfile(load_url) is True

    results = tmp_path / "out"
    results.mkdir()
    piece = FetchEnergyDataPiece.__new__(FetchEnergyDataPiece)
    piece.results_path = str(results)
    out = piece.piece_function(
        FetchInput(load_csv=load_url, prices_csv=f"{base}/missing_prices.csv"),
        secrets_data=secrets,
    )

    # Output parquet is written to the local Domino results dir.
    assert out.output_path
    merged = pd.read_parquet(out.output_path)
    assert len(merged) == 3
    assert "load_kw" in merged.columns
