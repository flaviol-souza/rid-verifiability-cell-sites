"""Geometric descriptors that explain verifiability without running the channel.

All distances are horizontal, in a local frame around ONE common origin (the centroid of the full site inventory),
so maps and descriptors of different scenarios are directly comparable. Only drone positions are used.
"""
import numpy as np
import pandas as pd

from drs.geo import local_xy_m


def common_origin(all_sites: pd.DataFrame) -> tuple:
    """Origin shared by every scenario: centroid of the full inventory (never of a per-operator subset)."""
    return float(all_sites["lat"].mean()), float(all_sites["lon"].mean())


def kth_site_distance_m(sx, sy, x, y, k: int) -> np.ndarray:
    """Horizontal distance from each point to its k-th nearest site (inf if fewer than k sites)."""
    sx, sy, x, y = (np.asarray(v, dtype=float) for v in (sx, sy, x, y))
    if len(sx) < k:
        return np.full(len(x), np.inf)
    d = np.hypot(x[:, None] - sx[None, :], y[:, None] - sy[None, :])
    return np.partition(d, k - 1, axis=1)[:, k - 1]


def bbox_edge_distance_m(sx, sy, x, y) -> np.ndarray:
    """Distance from each point to the edge of the site bounding box (> 0 inside, ≤ 0 outside).

    The ANATEL extract covers at least this box, so a point farther than R from its edge cannot lose a site within R
    to the inventory boundary: dist > R ⇒ untruncated at range R (conservative)."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    x0, x1, y0, y1 = np.min(sx), np.max(sx), np.min(sy), np.max(sy)
    return np.minimum.reduce([x - x0, x1 - x, y - y0, y1 - y])


def weighted_median(v, w) -> float:
    v, w = np.asarray(v, dtype=float), np.asarray(w, dtype=float)
    if len(v) == 0:
        return float("nan")
    o = np.argsort(v, kind="mergesort")
    c = np.cumsum(w[o])
    return float(v[o][np.searchsorted(c, 0.5 * c[-1])])


def session_geometry(samples: pd.DataFrame, sites: pd.DataFrame, all_sites: pd.DataFrame, w: pd.Series,
                     k: int, range_m: float) -> pd.DataFrame:
    """Per session: time-weighted median distance to the k-th nearest site of `sites`, and the fraction of flight time
    within range_m of the inventory edge (where the extract may hide sites)."""
    lat0, lon0 = common_origin(all_sites)
    x, y = local_xy_m(samples["lat"], samples["lon"], lat0, lon0)
    sx, sy = local_xy_m(sites["lat"], sites["lon"], lat0, lon0)
    ax_, ay_ = local_xy_m(all_sites["lat"], all_sites["lon"], lat0, lon0)
    dk = kth_site_distance_m(sx, sy, x, y, k)
    edge = bbox_edge_distance_m(ax_, ay_, x, y) < range_m
    df = pd.DataFrame({"session_id": samples["session_id"].to_numpy(), "uas_id": samples["uas_id"].to_numpy(),
                       "dk": dk, "edge": edge.astype(float), "w": w.to_numpy()})
    rows = []
    for (sid, uid), g in df.groupby(["session_id", "uas_id"], sort=True):
        rows.append({"session_id": sid, "uas_id": uid, f"d{k}_median_m": weighted_median(g["dk"], g["w"]),
                     "frac_time_inventory_edge": float((g["edge"] * g["w"]).sum() / g["w"].sum()),
                     "time_s": float(g["w"].sum())})
    return pd.DataFrame(rows)
