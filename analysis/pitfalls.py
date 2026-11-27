"""Section 4 pitfall statistics (drone-pilot distance, position hold time, position jump).

Pure function. Input is one row per kept drone sample with the pilot position joined by exact (session, time) equality.
Only three medians leave this module; no pilot position is returned or written.
"""
import numpy as np
import pandas as pd

MAX_SPEED_MS = 40.0  # same rule as cleaning step C9


def pitfall_stats(messages: pd.DataFrame) -> dict:
    """messages: columns flight, t (datetime), x, y (drone, metres), px, py (pilot, metres; NaN if absent)."""
    m = messages.sort_values(["flight", "t"])
    pil = m.dropna(subset=["px", "py"])
    pilot = np.hypot(pil.x - pil.px, pil.y - pil.py)
    new = (m.x != m.groupby("flight").x.shift()) | (m.y != m.groupby("flight").y.shift())
    m = m.assign(run=new.groupby(m.flight).cumsum())
    r = m.groupby(["flight", "run"]).agg(t0=("t", "first"), x=("x", "first"), y=("y", "first")).reset_index()
    r["tn"] = r.groupby("flight").t0.shift(-1)
    r["xn"] = r.groupby("flight").x.shift(-1)
    r["yn"] = r.groupby("flight").y.shift(-1)
    r = r.dropna(subset=["tn"])
    r["hold"] = (r.tn - r.t0).dt.total_seconds()
    r["jump"] = np.hypot(r.xn - r.x, r.yn - r.y)
    n_changes = len(r)
    r = r[r.jump / r.hold < MAX_SPEED_MS]
    return {"desc_pilot_distance_median_m": float(np.median(pilot)),
            "desc_hold_median_s": float(r.hold.median()),
            "desc_hold_jump_median_m": float(r.jump.median()),
            "_n_flights": int(m.flight.nunique()),
            "_repeat_share": float((~new).mean()),
            "_n_position_changes": int(n_changes),
            "_n_speed_discarded": int(n_changes - len(r)),
            "_pilot_found_share": float(messages[["px", "py"]].notna().all(axis=1).mean()),
            "_n_samples": int(len(messages))}


def load_pitfall_input(interim_dir) -> pd.DataFrame:
    """Join pilot positions to drone samples by exact (session_id, t_utc); local equirectangular metres."""
    from pathlib import Path
    d = Path(interim_dir)
    s = pd.read_parquet(d / "samples.parquet")
    g = pd.read_parquet(d / "ground_refs.parquet")
    p = g[g.role == "pilot"].drop_duplicates(["session_id", "t_utc"])
    p = p[["session_id", "t_utc", "lat", "lon"]].rename(columns={"lat": "plat", "lon": "plon"})
    m = s.merge(p, on=["session_id", "t_utc"], how="left")
    lat0, lon0, k = m.lat.mean(), m.lon.mean(), 6371008.8
    def xy(lon, lat):
        return np.radians(lon - lon0) * np.cos(np.radians(lat0)) * k, np.radians(lat - lat0) * k
    m["x"], m["y"] = xy(m.lon, m.lat)
    m["px"], m["py"] = xy(m.plon, m.plat)
    m = m.rename(columns={"session_id": "flight", "t_utc": "t"})
    m["t"] = pd.to_datetime(m["t"])
    return m[["flight", "t", "x", "y", "px", "py"]]
