"""Drone track + sites → one row per (sample, candidate site): received power and heard/unheard.

Candidate sites: every site within r_max_m (horizontal) of the sample. Sites are never clipped by the RoI.
Unheard pairs are recorded as unheard (never dropped). Reads only the drone track (no pilot/home positions).
"""
import numpy as np
import pandas as pd

from drs.channel import pathloss, shadowing
from drs.geo import local_xy_m

OBS_COLS = ["sample_id", "session_id", "site_id", "dx_m", "dy_m", "dh_m", "d3_m", "mean_dbm", "rssi_dbm", "heard"]


def candidate_pairs(samples: pd.DataFrame, sites: pd.DataFrame, r_max_m: float, h_rx_m: float):
    lat0, lon0 = float(sites["lat"].mean()), float(sites["lon"].mean())
    sx, sy = local_xy_m(samples["lat"], samples["lon"], lat0, lon0)
    tx, ty = local_xy_m(sites["lat"], sites["lon"], lat0, lon0)
    dx = sx[:, None] - tx[None, :]
    dy = sy[:, None] - ty[None, :]
    dh = np.hypot(dx, dy)
    i, j = np.nonzero(dh <= r_max_m)
    dz = samples["agl_m"].to_numpy()[i] - h_rx_m
    return i, j, dx[i, j], dy[i, j], dh[i, j], np.sqrt(dh[i, j] ** 2 + dz ** 2), (sx, sy)


def path_distance_m(samples: pd.DataFrame, sx: np.ndarray, sy: np.ndarray) -> np.ndarray:
    """Cumulative horizontal distance travelled within each session (samples sorted by session, time)."""
    step = np.hypot(np.diff(sx, prepend=sx[:1]), np.diff(sy, prepend=sy[:1]))
    first = samples["session_id"].ne(samples["session_id"].shift()).to_numpy()
    step[first] = 0.0
    return pd.Series(step).groupby(samples["session_id"].to_numpy()).cumsum().to_numpy()


def observe(samples: pd.DataFrame, sites: pd.DataFrame, ch: dict, seed: int) -> pd.DataFrame:
    samples = samples.sort_values(["session_id", "t_utc"], kind="mergesort").reset_index(drop=True)
    sites = sites.sort_values("site_id", kind="mergesort").reset_index(drop=True)
    i, j, dx, dy, dh, d3, (sx, sy) = candidate_pairs(samples, sites, ch["r_max_m"], ch["sniffer_height_m"])
    s_path = path_distance_m(samples, sx, sy)
    obs = pd.DataFrame({"_i": i, "sample_id": samples["sample_id"].to_numpy()[i],
                        "session_id": samples["session_id"].to_numpy()[i],
                        "site_id": sites["site_id"].to_numpy()[j], "dx_m": dx, "dy_m": dy, "dh_m": dh, "d3_m": d3, "_s": s_path[i]})
    obs["mean_dbm"] = pathloss.mean_rx_dbm(obs["d3_m"], ch)
    obs = obs.sort_values(["session_id", "site_id", "_i"], kind="mergesort").reset_index(drop=True)
    x = np.empty(len(obs))
    for (sess, site), idx in obs.groupby(["session_id", "site_id"], sort=True).indices.items():
        idx = np.sort(idx)
        ds = np.diff(obs["_s"].to_numpy()[idx], prepend=obs["_s"].to_numpy()[idx][0])
        x[idx] = shadowing.ar1_series(ds, ch["shadow_sigma_db"], ch["shadow_dcorr_m"],
                                      shadowing.link_seed(seed, sess, site))
    obs["rssi_dbm"] = obs["mean_dbm"] + x
    obs["heard"] = obs["rssi_dbm"] >= ch["sniffer_sens_dbm"]
    obs = obs.sort_values(["_i", "site_id"], kind="mergesort").reset_index(drop=True)
    return obs[OBS_COLS]
