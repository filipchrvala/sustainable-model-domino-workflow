"""
Vygeneruje Solargis TS15 CSV na celý kalendárny rok 2025 (15 min, 35 040 riadkov).

Vychádza z existujúceho vzorku tests/SolarSimPiece_Inputs/SolarGIS.csv (krátky export),
ktorý sa cyklicky opakuje a mierne sa škáluje podľa dňa v roku (leto/jar).

Výstup: tests/SolarSimPiece_Inputs/SolarGIS_2025.csv

Spustenie z koreňa projektu:
  python scripts/generate_solargis_year_2025.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = PROJECT_ROOT / "tests" / "SolarSimPiece_Inputs" / "SolarGIS.csv"
OUT = PROJECT_ROOT / "tests" / "SolarSimPiece_Inputs" / "SolarGIS_2025.csv"

HEADER_LINES = """#15 MINUTE VALUES OF SOLAR RADIATION AND METEOROLOGICAL PARAMETERS AND PV OUTPUT
#
#File type: Solargis_TS15
#Customer name: SAV
#Issued: 2025-01-01 00:00
#
#Site name: PVPP_IMMS_CIS, Slovakia (SK)
#Latitude: 48.170878
#Longitude: 17.069268
#Elevation: 179.0 m a.s.l.
#
#Summarization type: harmonized to 15 min
#Summarization period: 01/01/2025 - 31/12/2025 (generated)
#Spatial resolution: 250 m
#
#Columns:
#Date - Date of measurement, format DD.MM.YYYY
#Time - Time of measurement, time reference UTC+1, time step 15 min, time format HH:MM
#GHI - Global horizontal irradiance [W/m2]
#DNI - Direct normal irradiance [W/m2]
#DIF - Diffuse horizontal irradiance [W/m2]
#GTI - Global tilted irradiance [W/m2]
#SE - Sun altitude angle [deg]
#SA - Sun aspect angle [deg]
#PVOUT - PV output [kW]
#TEMP - Air temperature at 2 m [deg_C]
#WS - Wind speed at 10 m [m/s]
#WG - Wind gust at 10 m [m/s]
#WD - Wind direction at 10 m [deg]
#RH - Relative humidity [%]
#AP - Atmospheric pressure [hPa]
#PVOUT_UNC_LOW - low estimate of PVOUT [kW]
#PVOUT_UNC_HIGH - high estimate of PVOUT [kW]
#
#Data:
"""


def main() -> None:
    if not TEMPLATE.is_file():
        raise FileNotFoundError(f"Chýba šablóna {TEMPLATE}")

    tpl = pd.read_csv(TEMPLATE, sep=";", comment="#", engine="python")
    n_tpl = len(tpl)
    if n_tpl < 96:
        raise ValueError("Šablóna musí mať aspoň jeden deň 15-min dát")

    # Celý rok 2025: 365 dní × 96 = 35 040
    idx = pd.date_range("2025-01-01 00:00:00", "2025-12-31 23:45:00", freq="15min", tz=None)
    assert len(idx) == 35040, len(idx)

    # Jemná sezónna modulácia (deň ~172 = leto)
    doy = idx.dayofyear.to_numpy(dtype=float)
    seasonal = 0.55 + 0.45 * np.cos(2.0 * np.pi * (doy - 172.0) / 365.25)

    rows: list[list[object]] = []
    rad_cols = ["GHI", "DNI", "DIF", "GTI", "PVOUT", "PVOUT_UNC_LOW", "PVOUT_UNC_HIGH"]

    for i, ts in enumerate(idx):
        r = tpl.iloc[i % n_tpl].copy()
        s = float(seasonal[i])
        for c in rad_cols:
            if c in r.index and pd.notna(r[c]):
                v = float(r[c])
                r[c] = max(0.0, v * s)
        # teplota: mierny posun podľa ročného cyklu (orientačne)
        if "TEMP" in r.index and pd.notna(r["TEMP"]):
            r["TEMP"] = float(r["TEMP"]) + 8.0 * np.sin(2.0 * np.pi * (doy[i] - 80.0) / 365.25)

        date_str = ts.strftime("%d.%m.%Y")
        time_str = ts.strftime("%H:%M")
        row_out = [date_str, time_str]
        for col in tpl.columns:
            if col in ("Date", "Time"):
                continue
            row_out.append(r[col])
        rows.append(row_out)

    cols = ["Date", "Time"] + [c for c in tpl.columns if c not in ("Date", "Time")]
    out_df = pd.DataFrame(rows, columns=cols)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        f.write(HEADER_LINES)
        f.write(";".join(out_df.columns) + "\n")
        out_df.to_csv(f, sep=";", index=False, header=False, lineterminator="\n")

    print(f"OK: {OUT} ({len(out_df)} riadkov = 365 dní × 96)")


if __name__ == "__main__":
    main()
