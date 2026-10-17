"""RQ1: aggregates that describe the logs. PRIVACY: outputs never contain positions, only counts and quantiles.

Inputs: samples.parquet (drone track) and ground_refs.parquet (pilot/home rows, private). Pilot/home positions are
used only to compute distances to the drone, which are reported as quantiles.
"""
import numpy as np
import pandas as pd

from drs.geo import haversine_m

QUANTILES = [0.05, 0.25, 0.5, 0.75, 0.95]
FORBIDDEN_COLUMNS = {"lat", "lon", "latitude", "longitude", "x", "y"}


def _q(series: pd.Series, name: str) -> dict:
    s = pd.Series(series).dropna()
    out = {"quantity": name, "n": int(len(s))}
    out.update({f"p{int(q * 100)}": (round(float(s.quantile(q)), 2) if len(s) else np.nan) for q in QUANTILES})
    return out


def role_table(samples: pd.DataFrame, refs: pd.DataFrame) -> pd.DataFrame:
    rows = [{"role": "drone", "rows": len(samples), **{k: v for k, v in _q(samples["agl_dem_m"], "agl_dem_m").items() if k != "quantity"}}]
    for role, g in refs.groupby("role", sort=True):
        rows.append({"role": role, "rows": len(g), **{k: v for k, v in _q(g["agl_dem_m"], "agl_dem_m").items() if k != "quantity"}})
    return pd.DataFrame(rows)


def group_size_table(samples: pd.DataFrame) -> pd.DataFrame:
    return samples["group_size"].value_counts().sort_index().rename_axis("group_size").reset_index(name="messages")


def drone_ref_distances(samples: pd.DataFrame, refs: pd.DataFrame) -> pd.DataFrame:
    """Quantiles of the drone–pilot and drone–home distances at the same (uas_id, t_utc)."""
    rows = []
    d = samples[["uas_id", "t_utc", "lat", "lon"]]
    for role in ("pilot", "home", "ground_ref"):
        r = refs.loc[refs["role"] == role, ["uas_id", "t_utc", "lat", "lon"]]
        m = d.merge(r, on=["uas_id", "t_utc"], suffixes=("_d", "_r"))
        dist = haversine_m(m["lat_d"], m["lon_d"], m["lat_r"], m["lon_r"])
        rows.append(_q(pd.Series(dist), f"distance_drone_{role}_m"))
    return pd.DataFrame(rows)


def hold_durations(samples: pd.DataFrame) -> pd.DataFrame:
    """Time (s) a reported position is held before it changes, within sessions."""
    s = samples.sort_values(["session_id", "t_utc"], kind="mergesort")
    changed = (s["lat"].diff().ne(0) | s["lon"].diff().ne(0)) | s["session_id"].ne(s["session_id"].shift())
    starts = s.loc[changed, ["session_id", "t_utc"]]
    holds = starts.groupby("session_id")["t_utc"].diff().dt.total_seconds().dropna()
    steps = s.groupby("session_id")["t_utc"].diff().dt.total_seconds().dropna()
    return pd.DataFrame([_q(holds, "position_hold_s"), _q(steps, "logging_interval_s"),
                         {"quantity": "frac_steps_without_position_change", "n": int(len(steps)),
                          "p50": round(float(1 - (changed.sum() - s["session_id"].nunique()) / max(len(steps), 1)), 4)}])


def session_table(samples: pd.DataFrame) -> pd.DataFrame:
    g = samples.groupby("session_id")
    dur = (g["t_utc"].max() - g["t_utc"].min()).dt.total_seconds()
    per_serial = samples.groupby("uas_id")["session_id"].nunique()
    days = samples.assign(day=samples["t_utc"].dt.date).groupby("uas_id")["day"].nunique()
    return pd.DataFrame([_q(dur, "session_duration_s"), _q(per_serial, "sessions_per_serial"),
                         {"quantity": "serials_seen_on_more_than_one_day", "n": int(len(days)), "p50": int((days > 1).sum())},
                         {"quantity": "frac_samples_in_roi", "n": int(len(samples)), "p50": round(float(samples["in_roi"].mean()), 4)}])


def characterize(samples: pd.DataFrame, refs: pd.DataFrame) -> dict:
    out = {"roles": role_table(samples, refs), "group_sizes": group_size_table(samples),
           "distances": drone_ref_distances(samples, refs), "holds": hold_durations(samples),
           "sessions": session_table(samples)}
    for name, df in out.items():
        leak = FORBIDDEN_COLUMNS & {c.lower() for c in df.columns}
        if leak:
            raise RuntimeError(f"characterization table '{name}' would expose positions: {leak}")
    return out
