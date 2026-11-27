"""R3 — cleaning rules C1–C6, C8, C9 with an accounting log (C7 lives in agl.py). Rules version v2."""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from shapely import contains_xy
from shapely.geometry.base import BaseGeometry

from drs.geo import haversine_m


@dataclass
class CleaningLog:
    rows: list = field(default_factory=list)

    def record(self, rule: str, before: pd.DataFrame, after: pd.DataFrame, id_col: str = "uas_id") -> None:
        affected = sorted(set(before[id_col]) - set(after[id_col])) if len(after) < len(before) else []
        self.rows.append({"rule": rule, "rows_before": len(before), "rows_dropped": len(before) - len(after),
                          "rows_after": len(after), "serials_removed": len(affected)})

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=["rule", "rows_before", "rows_dropped", "rows_after", "serials_removed"])


def c1_exact_duplicates(df):
    return df.drop_duplicates().reset_index(drop=True)


def c2_split_roles(df):
    """C2 v2. Each (uas_id, t_utc) message carries up to three positions, in a fixed file order
    (diagnostic G0-v1, audit N11): 1st = drone, 2nd = pilot/operator, 3rd = home (take-off point).
    Returns (drone_track, ground_refs). In groups of two, the 2nd row is a generic ground reference.
    Requires file order to be preserved up to this point (C1 keeps the first occurrence)."""
    df = df.copy()
    g = df.groupby(["uas_id", "t_utc"], sort=False)
    ordinal = g.cumcount().to_numpy() + 1
    size = g["uas_id"].transform("size").to_numpy()
    role = np.full(len(df), "ground_ref", dtype=object)
    role[ordinal == 1] = "drone"
    role[(size >= 3) & (ordinal == 2)] = "pilot"
    role[(size >= 3) & (ordinal == 3)] = "home"
    role[ordinal >= 4] = "unknown"
    df["group_size"] = size
    df["role"] = role
    drone = df[df["role"] == "drone"].drop(columns="role").reset_index(drop=True)
    refs = df[df["role"] != "drone"].reset_index(drop=True)
    return drone, refs


def c3_outside_extent(df, extent: BaseGeometry):
    """C3 v2. Drop serials with no sample inside the extent of the site inventory (bounding box of the
    unique ANATEL sites), e.g. a serial logged in another city. Samples near but outside the analysis
    domain are left to C8, so the log attributes each removal to the right rule."""
    inside = contains_xy(extent, df["lon"].to_numpy(), df["lat"].to_numpy())
    keep_ids = set(df.loc[inside, "uas_id"])
    return df[df["uas_id"].isin(keep_ids)].reset_index(drop=True)


def c4_placeholders(df):
    """Drop serials with a single timestamp AND a single position (placeholders such as 'MissionAlpha').
    Rule-based on purpose: names are pseudonymized before cleaning."""
    g = df.groupby("uas_id")
    n_t = g["t_utc"].nunique()
    n_pos = g[["lat", "lon", "alt"]].apply(lambda x: len(x.drop_duplicates()))
    placeholders = set(n_t[(n_t == 1) & (n_pos == 1)].index)
    return df[~df["uas_id"].isin(placeholders)].reset_index(drop=True)


def c5_sentinel_altitude(df, min_alt_msl_m: float):
    return df[df["alt"] >= min_alt_msl_m].reset_index(drop=True)


def c6_sessionize(df, gap_s: float):
    df = df.sort_values(["uas_id", "t_utc"], kind="mergesort").reset_index(drop=True)
    gaps = df.groupby("uas_id")["t_utc"].diff().dt.total_seconds()
    k = (gaps > gap_s).groupby(df["uas_id"]).cumsum().astype(int)
    df["session_id"] = df["uas_id"] + "_s" + k.map("{:03d}".format)
    return df


def c8_domain_and_roi(df, domain: BaseGeometry, roi: BaseGeometry, min_agl_m: float):
    x, y = df["lon"].to_numpy(), df["lat"].to_numpy()
    keep = contains_xy(domain, x, y) & (df["agl_m"].to_numpy() > min_agl_m)
    out = df[keep].copy()
    out["in_roi"] = contains_xy(roi, out["lon"].to_numpy(), out["lat"].to_numpy())
    return out.reset_index(drop=True)


def _walk_speeds(df, vmax_mps: float, estimator: str):
    """Shared walk for C9 and the G0 speed statistics.
    'since_first_seen' (v2): positions are logged in steps (the position is held for several seconds and
    then jumps), so the displacement to a new position is divided by the time since the previous retained
    position was FIRST reported. 'consecutive' (v1, diagnostic only): divides by the time since the
    previous retained sample. Repeated positions are never excluded."""
    if estimator not in ("since_first_seen", "consecutive"):
        raise ValueError(f"unknown C9 estimator: {estimator}")
    keep = np.ones(len(df), dtype=bool)
    speeds = []
    t = df["t_utc"].to_numpy(dtype="datetime64[ns]").astype(np.int64) / 1e9
    lat, lon = df["lat"].to_numpy(), df["lon"].to_numpy()
    for _, idx in df.groupby("session_id", sort=False).indices.items():
        idx = np.sort(idx)
        last = idx[0]
        t_first = t[last]
        for i in idx[1:]:
            d = float(haversine_m(lat[last], lon[last], lat[i], lon[i]))
            if d == 0.0:
                last = i
                continue
            dt = t[i] - (t_first if estimator == "since_first_seen" else t[last])
            v = d / dt if dt > 0 else np.inf
            if v > vmax_mps:
                keep[i] = False
                continue
            speeds.append(v)
            last, t_first = i, t[i]
    return keep, np.array(speeds)


def c9_speed(df, vmax_mps: float, estimator: str = "since_first_seen"):
    """C9. Exclude a sample whose implied ground speed from the last retained position exceeds vmax.
    A single GNSS spike is removed without removing the good sample that follows it."""
    keep, _ = _walk_speeds(df, vmax_mps, estimator)
    return df[keep].reset_index(drop=True)


def implied_speeds(df, estimator: str = "since_first_seen"):
    """Speeds at position changes (no exclusion), for the G0 table."""
    _, v = _walk_speeds(df, np.inf, estimator)
    return v
