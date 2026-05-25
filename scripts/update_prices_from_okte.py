"""
Aktualizuje prices.csv z OKTE 2026 a 2025.xlsx (reálne ceny elektriny).
Extrahuje obdobie 2025-03-20 .. 2025-04-03 (1440 x 15 min), konvertuje EUR/MWh -> EUR/kWh.
"""
import pandas as pd
from pathlib import Path

base = Path(__file__).resolve().parent
fetch_in = base / "FetchEnergyDataPiece_Inputs"
xlsx_path = fetch_in / "OKTE 2026 a 2025.xlsx"
out_path = fetch_in / "prices.csv"

# Obdobie zhodné s load/production (virtual_solar)
target_start = "2025-03-20 00:00:00"
target_end = "2025-04-03 23:45:00"
n_rows = 1440  # 15 dní * 96

df = pd.read_excel(xlsx_path, sheet_name="2025", header=0)
df.columns = ["datetime", "price_eur_mwh"]
df = df.dropna(subset=["datetime"])
df["datetime"] = pd.to_datetime(df["datetime"])

mask = (df["datetime"] >= target_start) & (df["datetime"] <= target_end)
df = df.loc[mask].copy()

# Zarovnanie na presne 1440 intervalov (15-min mriežka)
grid = pd.date_range(target_start, periods=n_rows, freq="15min")
df = df.set_index("datetime")
df = df.reindex(grid).ffill().bfill()  # ffill/bfill ak OKTE má menej riadkov
df = df.reset_index()
df.columns = ["datetime", "price_eur_mwh"]
df["price_eur_kwh"] = df["price_eur_mwh"] / 1000.0

out = df[["datetime", "price_eur_kwh"]].copy()
out["datetime"] = out["datetime"].dt.strftime("%Y-%m-%d %H:%M")
out.to_csv(out_path, index=False)
print(f"Updated {out_path}: {len(out)} rows, {out['datetime'].iloc[0]} -> {out['datetime'].iloc[-1]}")
print(f"Price range: {out['price_eur_kwh'].min():.4f} - {out['price_eur_kwh'].max():.4f} EUR/kWh")
