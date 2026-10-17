"""R2 — one row per unique cell site (never clipped by the RoI)."""
import pandas as pd


def collapse_sites(anatel: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame({
        "lat": pd.to_numeric(anatel["Latitude decimal"].astype(str).str.replace(",", ".")),
        "lon": pd.to_numeric(anatel["Longitude decimal"].astype(str).str.replace(",", ".")),
        "operator": anatel["Empresa Estação"].astype(str).str.strip(),
        "record": anatel["Número Estação"].astype(str).str.strip(),
    })
    df["lat"], df["lon"] = df["lat"].round(6), df["lon"].round(6)
    g = (df.groupby(["lat", "lon"], sort=True)
           .agg(operator=("operator", lambda s: "|".join(sorted(set(s)))),
                n_records=("record", "size"),
                records=("record", lambda s: "|".join(sorted(set(s)))))
           .reset_index())
    g.insert(0, "site_id", [f"site_{i:03d}" for i in range(len(g))])
    return g
