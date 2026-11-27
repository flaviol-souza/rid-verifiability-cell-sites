"""Summary tables from a block's session_metrics: mean over sessions (seeds averaged first) with a 95% cluster
bootstrap CI by serial, and a per-serial breakdown (weights) so that no serial dominates unseen."""
import pandas as pd

from analysis import hypotheses as hy
from analysis import stats


def summary_table(tbl: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    sm = hy.session_means(tbl)
    rows = []
    for (fam, sc, R, metric), g in sm.groupby(["family", "scenario", "range_m", "metric"], sort=True):
        est, lo, hi = stats.cluster_bootstrap_ci(g["value"], g["uas_id"], seed=seed)
        per_serial = g.groupby("uas_id")["value"].mean()                  # every drone weighs the same
        s_est, s_lo, s_hi = stats.cluster_bootstrap_ci(per_serial, per_serial.index, seed=seed)
        top = g["uas_id"].value_counts(normalize=True).iloc[0]
        rows.append({"family": fam, "scenario": sc, "range_m": R, "metric": metric, "n_sessions": len(g),
                     "n_serials": g["uas_id"].nunique(), "mean": est, "ci_lo": lo, "ci_hi": hi,
                     "serial_weighted_mean": s_est, "serial_ci_lo": s_lo, "serial_ci_hi": s_hi,
                     "top_serial_session_share": round(float(top), 4)})
    return pd.DataFrame(rows)


def per_serial_table(tbl: pd.DataFrame, family: str, scenario: str, range_m: float, metric: str) -> pd.DataFrame:
    sm = hy.session_means(tbl)
    g = sm[(sm["family"] == family) & (sm["scenario"] == scenario) & (sm["range_m"] == range_m) & (sm["metric"] == metric)]
    out = g.groupby("uas_id").agg(n_sessions=("session_id", "nunique"), mean=("value", "mean")).reset_index()
    out["session_share"] = out["n_sessions"] / out["n_sessions"].sum()
    return out.sort_values("n_sessions", ascending=False).reset_index(drop=True)
