"""C7 — the ONLY place where the MSL altitude is converted (structure.md, rule 5)."""
import numpy as np
import pandas as pd
import rasterio


class DemCoverageError(RuntimeError):
    pass


def add_agl(df: pd.DataFrame, dem_path: str) -> pd.DataFrame:
    with rasterio.open(dem_path) as src:
        b = src.bounds
        outside = ~(df["lon"].between(b.left, b.right) & df["lat"].between(b.bottom, b.top))
        if outside.any():   # rasterio returns 0 (not NaN) outside the raster when nodata is unset
            raise DemCoverageError(f"{int(outside.sum())} samples outside DEM bounds")
        elev = np.array([v[0] for v in src.sample(zip(df["lon"], df["lat"]))], dtype=float)
        if src.nodata is not None:
            elev[elev == src.nodata] = np.nan
    if np.isnan(elev).any():
        raise DemCoverageError(f"{int(np.isnan(elev).sum())} samples outside DEM coverage")
    out = df.copy()
    out["agl_m"] = out.pop("alt").to_numpy() - elev   # MSL column removed here
    return out
