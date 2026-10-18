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

    ASSUMPTION (not established by the extract's provenance): the inventory is complete inside this box. Only under
    that assumption does dist > R imply that no site within R was lost to the inventory boundary. If the extract was
    restricted by some other geometry, this flag can miss truncation; report it as "no evidence of edge truncation"."""
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


def geometric_sigma_h(samples: pd.DataFrame, sites: pd.DataFrame, range_m: float, h_rx_m: float, eta: float,
                      sigma_db: float) -> np.ndarray:
    """Per sample: CRLB σ_h (known power) using every site whose 3D distance is within the implied range R, i.e. the
    links heard on average, without shadowing. Returns (σ_h, number of such sites); σ_h is inf when fewer than 2 sites
    or degenerate geometry.
    Explains V3 from geometry alone; it is not a substitute for the simulated V3."""
    from analysis import verifiability as vf
    from drs.channel import observe
    i, j, dx, dy, _dh, d3, _ = observe.candidate_pairs(samples, sites, range_m, h_rx_m)
    keep = d3 <= range_m
    obs = pd.DataFrame({"sample_id": samples["sample_id"].to_numpy()[i[keep]], "dx_m": dx[keep], "dy_m": dy[keep],
                        "d3_m": d3[keep], "heard": True})
    pb = vf.per_sample_bounds_fast(obs, eta, sigma_db).set_index("sample_id")
    sid = samples["sample_id"]
    return sid.map(pb["sigma_h_v3_m"]).fillna(np.inf).to_numpy(), sid.map(pb["n_obs"]).fillna(0).astype(int).to_numpy()


def crlb_range_limit_m(scale_m: float, n_sites: int, eta: float, sigma_db: float) -> float:
    """Largest common distance d at which n_sites in symmetric geometry still give σ_h ≤ scale_m:
    σ_h = 2 d / (b √n), b = 10 η / (σ ln 10)  ⇒  d_max = scale · b · √n / 2."""
    b = 10.0 * eta / (sigma_db * np.log(10.0))
    return float(scale_m * b * np.sqrt(n_sites) / 2.0)
