"""RQ2: observer counts, time-weighted observable fractions and structural shadow windows."""
import numpy as np
import pandas as pd


def n_observers(samples: pd.DataFrame, obs: pd.DataFrame) -> pd.Series:
    heard = obs[obs["heard"]].groupby("sample_id").size()
    return samples["sample_id"].map(heard).fillna(0).astype(int).rename("n_obs")


def time_weights_s(samples: pd.DataFrame, gap_cap_s: float) -> pd.Series:
    """Each sample stands for the time until the next sample of its session (capped at T_gap).
    The last sample of a session gets the session's median interval."""
    s = samples.sort_values(["session_id", "t_utc"], kind="mergesort")
    nxt = s.groupby("session_id")["t_utc"].shift(-1)
    w = (nxt - s["t_utc"]).dt.total_seconds()
    med = w.groupby(s["session_id"]).transform("median")
    w = w.fillna(med).fillna(1.0).clip(upper=gap_cap_s)
    return w.reindex(samples.index)


def observable_fraction(samples: pd.DataFrame, n_obs: pd.Series, w: pd.Series, k: int) -> pd.Series:
    """Per session: time-weighted fraction with |S| ≥ k."""
    ok = (n_obs >= k).astype(float)
    return (ok * w).groupby(samples["session_id"]).sum() / w.groupby(samples["session_id"]).sum()


def shadow_windows(samples: pd.DataFrame, flag_ok: pd.Series, w: pd.Series) -> pd.DataFrame:
    """Maximal runs of samples where flag_ok is False, within a session: duration (s) and sample count."""
    s = samples.assign(_ok=flag_ok.to_numpy(), _w=w.to_numpy()).sort_values(["session_id", "t_utc"], kind="mergesort")
    new_run = (s["_ok"] != s["_ok"].shift()) | (s["session_id"] != s["session_id"].shift())
    s["_run"] = new_run.cumsum()
    bad = s[~s["_ok"]]
    out = bad.groupby("_run").agg(session_id=("session_id", "first"), start=("t_utc", "first"),
                                  n_samples=("_w", "size"), duration_s=("_w", "sum"))
    return out.reset_index(drop=True)
