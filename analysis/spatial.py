"""Where verification works: per-sample flags aggregated on a regular grid (drone positions only; pilot/home never used).

Cells report time-weighted fractions (observable, V3) and the time spent there. Drone tracks are published data,
so cell-level aggregates are safe to publish.
"""
import numpy as np
import pandas as pd

from drs.geo import local_xy_m


def grid_cells(samples: pd.DataFrame, flags: dict, w: pd.Series, lat0: float, lon0: float, cell_m: float) -> pd.DataFrame:
    x, y = local_xy_m(samples["lat"], samples["lon"], lat0, lon0)
    ix, iy = np.floor(x / cell_m).astype(int), np.floor(y / cell_m).astype(int)
    df = pd.DataFrame({"ix": ix, "iy": iy, "w": w.to_numpy()})
    for name, f in flags.items():
        df[name] = np.asarray(f, dtype=float) * df["w"]
    g = df.groupby(["ix", "iy"], sort=True)
    out = g["w"].sum().rename("time_s").to_frame()
    for name in flags:
        out[f"frac_{name}"] = g[name].sum() / out["time_s"]
    out = out.reset_index()
    out["cell_x_m"] = (out["ix"] + 0.5) * cell_m
    out["cell_y_m"] = (out["iy"] + 0.5) * cell_m
    return out
