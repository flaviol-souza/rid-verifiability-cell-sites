"""R3 — cleaning rules C1–C6, C8, C9 with an accounting log (C7 lives in agl.py)."""
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


def c2_one_per_timestamp(df):
    """Keep the first row (file order) for each (uas_id, t_utc)."""
    return df.drop_duplicates(["uas_id", "t_utc"], keep="first").reset_index(drop=True)


def c3_outside_extent(df, domain: BaseGeometry):
    """Drop serials with no sample inside the analysis domain (e.g., a serial logged in another city)."""
    inside = contains_xy(domain, df["lon"].to_numpy(), df["lat"].to_numpy())
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


def c9_speed(df, vmax_mps: float):
    """Exclude a sample if its ground speed from the LAST RETAINED sample of the same session exceeds vmax.
    A single GNSS spike is removed without removing the good sample that follows it."""
    keep = np.ones(len(df), dtype=bool)
    for _, idx in df.groupby("session_id", sort=False).indices.items():
        idx = np.sort(idx)
        last = idx[0]
        for i in idx[1:]:
            dt = (df["t_utc"].iat[i] - df["t_utc"].iat[last]).total_seconds()
            d = haversine_m(df["lat"].iat[last], df["lon"].iat[last], df["lat"].iat[i], df["lon"].iat[i])
            if dt <= 0 or d / dt > vmax_mps:
                keep[i] = False
            else:
                last = i
    return df[keep].reset_index(drop=True)
