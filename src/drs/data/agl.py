"""C7 — the ONLY place where the MSL altitude is converted (structure.md, rule 5). Rules version v2.

v2 anchors the AGL of each session on a ground reference (audit N12): ground points (home, pilot)
sit at ≈ +6 m above the GLO-30 surface, so the raw difference alt − DEM is biased. For each session,
offset = median(alt − DEM) over its home rows; if the session has none, over its pilot/ground-reference
rows; otherwise no anchor (offset 0, flagged 'none'). agl_m = alt − DEM − offset.
The unanchored value is kept as agl_dem_m for the sensitivity analysis.
"""
import numpy as np
import pandas as pd
import rasterio

ANCHOR_PRIORITY = ("home", "pilot", "ground_ref")


class DemCoverageError(RuntimeError):
    pass


def _sample(dem_path: str, lon, lat, strict: bool = True) -> np.ndarray:
    lon, lat = np.asarray(lon, dtype=float), np.asarray(lat, dtype=float)
    with rasterio.open(dem_path) as src:
        b = src.bounds
        outside = ~((lon >= b.left) & (lon <= b.right) & (lat >= b.bottom) & (lat <= b.top))
        if strict and outside.any():   # rasterio returns 0 (not NaN) outside the raster when nodata is unset
            raise DemCoverageError(f"{int(outside.sum())} samples outside DEM bounds")
        elev = np.array([v[0] for v in src.sample(zip(lon, lat))], dtype=float) if len(lon) else np.array([])
        if src.nodata is not None:
            elev[elev == src.nodata] = np.nan
    elev[outside] = np.nan
    if strict and np.isnan(elev).any():
        raise DemCoverageError(f"{int(np.isnan(elev).sum())} samples outside DEM coverage")
    return elev


def anchor_offsets(refs: pd.DataFrame, dem_path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-session ground anchor. refs needs session_id, role, lat, lon, alt.
    Returns (offsets[session_id, agl_anchor, anchor_offset_m], refs with agl_dem_m)."""
    cols = ["session_id", "agl_anchor", "anchor_offset_m"]
    if refs is None or refs.empty:
        return pd.DataFrame(columns=cols), refs
    r = refs.copy()
    r["agl_dem_m"] = r["alt"].to_numpy() - _sample(dem_path, r["lon"], r["lat"], strict=False)
    r = r.dropna(subset=["agl_dem_m"])          # ground refs outside the DEM cannot anchor
    rows = []
    for sid, grp in r.groupby("session_id", sort=True):
        for role in ANCHOR_PRIORITY:
            vals = grp.loc[grp["role"] == role, "agl_dem_m"]
            if len(vals):
                rows.append((sid, role, float(np.median(vals))))
                break
    return pd.DataFrame(rows, columns=cols), r


def add_agl(df: pd.DataFrame, dem_path: str, refs: pd.DataFrame | None = None) -> pd.DataFrame:
    elev = _sample(dem_path, df["lon"], df["lat"], strict=True)
    out = df.copy()
    out["agl_dem_m"] = out.pop("alt").to_numpy() - elev        # MSL column removed here
    offsets, _ = anchor_offsets(refs, dem_path)
    out = out.merge(offsets, on="session_id", how="left", validate="many_to_one") if len(offsets) else \
        out.assign(agl_anchor=np.nan, anchor_offset_m=np.nan)
    out["agl_anchor"] = out["agl_anchor"].fillna("none")
    out["anchor_offset_m"] = out["anchor_offset_m"].astype(float).fillna(0.0)
    out["agl_m"] = out["agl_dem_m"] - out["anchor_offset_m"]
    return out
