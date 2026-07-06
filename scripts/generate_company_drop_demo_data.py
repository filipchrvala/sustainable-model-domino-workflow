"""Generate demo CSV files for sustainable ingest / incremental train."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LOAD_PATH = ROOT / "tests" / "WebUserInputPiece_Input" / "uploaded_load.csv"
DROP_DIR = ROOT / "tests" / "sustainable" / "company_drop"
WEB_APPEND_PATH = ROOT / "tests" / "WebUserInputPiece_Input" / "demo_append_spotreba.csv"


def make_week(start_dt: pd.Timestamp, seed: int) -> pd.DataFrame:
    base = pd.read_csv(LOAD_PATH, parse_dates=["datetime"])
    mean_load = float(base["load_kw"].mean())
    std_load = float(base["load_kw"].std())
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    t = start_dt + pd.Timedelta(minutes=15)
    for _ in range(96 * 7):
        hour = t.hour + t.minute / 60
        if 6 <= hour < 18:
            seasonal = 1.15 + 0.08 * np.sin(2 * np.pi * (hour - 6) / 12)
        elif 18 <= hour < 22:
            seasonal = 1.0
        else:
            seasonal = 0.72
        noise = rng.normal(0, std_load * 0.04)
        load = max(40.0, mean_load * seasonal + noise)
        if 6 <= hour < 22:
            price = 0.095 + rng.normal(0, 0.008)
        else:
            price = 0.075 + rng.normal(0, 0.005)
        price = float(np.clip(price, 0.05, 0.14))
        rows.append(
            {
                "datetime": t.strftime("%Y-%m-%d %H:%M:%S"),
                "department_id": "A",
                "load_kw": round(load, 3),
                "price_eur_kwh": round(price, 5),
            }
        )
        t += pd.Timedelta(minutes=15)
    return pd.DataFrame(rows)


def main() -> None:
    DROP_DIR.mkdir(parents=True, exist_ok=True)
    base = pd.read_csv(LOAD_PATH, parse_dates=["datetime"])
    last_dt = base["datetime"].max()
    start1 = last_dt.floor("D") + pd.Timedelta(days=1)

    batches = [
        ("company_update_2025_07_08.csv", start1, 101),
        ("company_update_2025_07_15.csv", start1 + pd.Timedelta(days=7), 202),
    ]
    for name, start, seed in batches:
        df = make_week(start, seed)
        path = DROP_DIR / name
        df.to_csv(path, index=False)
        print(f"{name}: {len(df)} rows, {df['datetime'].iloc[0]} .. {df['datetime'].iloc[-1]}")

    web_append = make_week(start1, 101).head(96)[["datetime", "load_kw", "price_eur_kwh"]]
    web_append = web_append.rename(columns={"price_eur_kwh": "price_eur_per_kwh"})
    WEB_APPEND_PATH.parent.mkdir(parents=True, exist_ok=True)
    web_append.to_csv(WEB_APPEND_PATH, index=False)
    print(f"web sample: {WEB_APPEND_PATH.name} ({len(web_append)} rows)")

    note = DROP_DIR / "POUZITIE.txt"
    note.write_text(
        "\n".join(
            [
                "Demo data na ingest / doucenie modelu (UC3.3)",
                "================================================",
                "",
                "Priečinok: tests/sustainable/company_drop/",
                "",
                "Súbory:",
                "  company_update_2025_07_08.csv  — 1 týždeň nových dát (nadväzuje na uploaded_load.csv)",
                "  company_update_2025_07_15.csv — ďalší týždeň (druhá dávka na opakovaný ingest)",
                "",
                "Formát CSV: datetime, department_id, load_kw, price_eur_kwh",
                "Oddelenie A — zhodné s model_registry a energy_history.",
                "",
                "Ako použiť:",
                "  1) Spusti celý workflow raz s hlavným CSV (uploaded_load.csv).",
                "  2) Nechaj JEDEN súbor v company_drop (alebo oba postupne).",
                "  3) Spusti workflow znova — kroky Sustainable ingest + Incremental train.",
                "     Alebo v dashboarde: Obnoviť data + alerty.",
                "",
                "Alternatíva cez web formulár:",
                "  tests/WebUserInputPiece_Input/demo_append_spotreba.csv",
                "  → nahrať v sekcii Nové riadky spotreby, zaškrtnúť Poslať do company_drop.",
                "",
                "Po ingeste sa súbory presunú do tests/sustainable/company_archive/.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"note: {note}")


if __name__ == "__main__":
    main()
