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


def hull_edge_distance_m(sx, sy, x, y) -> np.ndarray:
    """Distance from each point to the boundary of the convex hull of the sites (> 0 inside, < 0 outside).

    The extract was cut by a hand-drawn lat/lon polygon that contains every site. If that polygon is convex it contains
    the hull, so dist > R ⇒ no site within R can lie outside the cut (conservative). This is the inventory-edge test used
    by the analysis; the bounding box (bbox_edge_distance_m) over-states coverage at its empty corners."""
    from scipy.spatial import ConvexHull
    P = np.c_[np.asarray(sx, dtype=float), np.asarray(sy, dtype=float)]
    eq = ConvexHull(P).equations                       # n·p + b ≤ 0 inside, |n| = 1
    q = np.c_[np.asarray(x, dtype=float), np.asarray(y, dtype=float)]
    return -(q @ eq[:, :2].T + eq[:, 2]).max(axis=1)


def load_cut_ring(path):
    """Exterior ring (lon, lat) of the polygon used to cut the ANATEL extract, or None if the file is absent."""
    import json
    from pathlib import Path
    p = Path(path) if path else None
    if p is None or not p.exists():
        return None
    gj = json.loads(p.read_text())
    geom = gj["features"][0]["geometry"] if "features" in gj else gj.get("geometry", gj)
    if geom["type"] != "Polygon":
        raise ValueError("inventory cut must be a single Polygon")
    return np.asarray(geom["coordinates"][0], dtype=float)


def polygon_edge_distance_m(px, py, x, y) -> np.ndarray:
    """Signed distance from points to a simple polygon boundary (> 0 inside, < 0 outside); ring may be open or closed."""
    px, py = np.asarray(px, dtype=float), np.asarray(py, dtype=float)
    if px[0] == px[-1] and py[0] == py[-1]:
        px, py = px[:-1], py[:-1]
    x, y = np.asarray(x, dtype=float)[:, None], np.asarray(y, dtype=float)[:, None]
    ax, ay, bx, by = px[None, :], py[None, :], np.roll(px, -1)[None, :], np.roll(py, -1)[None, :]
    ex, ey = bx - ax, by - ay
    t = np.clip(((x - ax) * ex + (y - ay) * ey) / (ex * ex + ey * ey), 0.0, 1.0)
    dist = np.hypot(x - (ax + t * ex), y - (ay + t * ey)).min(axis=1)
    crosses = ((ay > y) != (by > y)) & (x < ax + (y - ay) * ex / np.where(ey == 0, np.inf, ey))
    inside = crosses.sum(axis=1) % 2 == 1
    return np.where(inside, dist, -dist)


def inventory_edge_distance_m(all_sites: pd.DataFrame, x, y, lat0: float, lon0: float, cut_ring=None):
    """Distance from points to the inventory edge: the documented cut polygon when available (exact), otherwise the
    convex hull of the sites (conservative if the cut is convex). Returns (distance, basis). Raises if any site lies
    outside the cut polygon, since that would contradict the extract's provenance."""
    ax_, ay_ = local_xy_m(all_sites["lat"], all_sites["lon"], lat0, lon0)
    if cut_ring is None:
        return hull_edge_distance_m(ax_, ay_, x, y), "site_hull"
    rx, ry = local_xy_m(cut_ring[:, 1], cut_ring[:, 0], lat0, lon0)
    if (polygon_edge_distance_m(rx, ry, ax_, ay_) < 0).any():
        raise ValueError("some ANATEL sites lie outside the documented cut polygon: check the polygon")
    return polygon_edge_distance_m(rx, ry, x, y), "cut_polygon"


def weighted_median(v, w) -> float:
    v, w = np.asarray(v, dtype=float), np.asarray(w, dtype=float)
    if len(v) == 0:
        return float("nan")
    o = np.argsort(v, kind="mergesort")
    c = np.cumsum(w[o])
    return float(v[o][np.searchsorted(c, 0.5 * c[-1])])


def session_geometry(samples: pd.DataFrame, sites: pd.DataFrame, all_sites: pd.DataFrame, w: pd.Series,
                     k: int, range_m: float, cut_ring=None) -> pd.DataFrame:
    """Per session: time-weighted median distance to the k-th nearest site of `sites`, and the fraction of flight time
    within range_m of the inventory edge (where the extract may hide sites)."""
    lat0, lon0 = common_origin(all_sites)
    x, y = local_xy_m(samples["lat"], samples["lon"], lat0, lon0)
    sx, sy = local_xy_m(sites["lat"], sites["lon"], lat0, lon0)
    dk = kth_site_distance_m(sx, sy, x, y, k)
    edge = inventory_edge_distance_m(all_sites, x, y, lat0, lon0, cut_ring)[0] < range_m
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


def inventory_bounded_sample_v3(samples: pd.DataFrame, sites: pd.DataFrame, observations: pd.DataFrame,
                                r_max_m: float, h_rx_m: float, eta: float, sigma_db: float,
                                scale_m: float, edge_distance_m: np.ndarray) -> pd.DataFrame:
    """Per-sample truncated/optimistic V3 and external-site lower bound.

    Heard links inside r_max form J_in. Every known inventory site beyond
    r_max contributes its exact directional Fisher matrix optimistically.
    """
    from analysis import verifiability as vf

    lat0, lon0 = common_origin(sites)
    x, y = local_xy_m(samples["lat"], samples["lon"], lat0, lon0)
    sx, sy = local_xy_m(sites["lat"], sites["lon"], lat0, lon0)
    heard = observations.loc[observations["heard"].astype(bool)]
    heard_groups = {sid: group for sid, group in heard.groupby("sample_id", sort=False)}
    b = 10.0 * eta / (sigma_db * np.log(10.0))
    rows = []
    for pos, sample in enumerate(samples.itertuples(index=False)):
        group = heard_groups.get(sample.sample_id)
        if group is None:
            J_in, n_in = np.zeros((2, 2)), 0
        else:
            J_in = vf.fisher_information_v3(group[["dx_m", "dy_m"]].to_numpy(), group["d3_m"].to_numpy(), eta, sigma_db)
            n_in = len(group)
        dx, dy = x[pos] - sx, y[pos] - sy
        d3 = np.sqrt(dx * dx + dy * dy + (float(sample.agl_m) - h_rx_m) ** 2)
        omitted = d3 > r_max_m
        J_omitted = vf.fisher_information_v3(np.c_[dx[omitted], dy[omitted]], d3[omitted], eta, sigma_db)
        decision = vf.inventory_bounded_decision(J_in, J_omitted, n_in, int(omitted.sum()), scale_m)
        n_star = vf.minimum_external_sites(J_in + J_omitted, float(edge_distance_m[pos]), b, scale_m,
                                           n_in + int(omitted.sum()))
        rows.append({"sample_id": sample.sample_id, "v3_lower": decision["lower"], "v3_upper": decision["upper"],
                     "sigma_h_opt_m": decision["sigma_h_opt_m"], "n_possible": n_in + int(omitted.sum()),
                     "n_star": n_star, "bound_diagnostic": decision["diagnostic"]})
    return pd.DataFrame(rows)
