"""H1–H3 evaluated from the per-session metrics table produced by the block runner.

Input table (long): scenario, range_m, family, seed, session_id, uas_id, metric, value
Seeds are averaged inside each session first (methods.md), then sessions are clustered by serial (uas_id).
"""
import numpy as np
import pandas as pd

from analysis import stats


def session_means(tbl: pd.DataFrame) -> pd.DataFrame:
    keys = ["family", "scenario", "range_m", "session_id", "uas_id", "metric"]
    return tbl.groupby(keys, as_index=False)["value"].mean()


def _wide(sm, family, range_m, metric):
    w = sm[(sm["family"] == family) & (sm["range_m"] == range_m) & (sm["metric"] == metric)]
    return w.pivot_table(index=["session_id", "uas_id"], columns="scenario", values="value").reset_index()


def h1_cooperation(sm: pd.DataFrame, family: str, k: int, alpha: float = 0.05, seed: int = 0) -> pd.DataFrame:
    """Shadow fraction (1 − observable_k) of the consortium vs the best single operator, per range; Holm over the grid."""
    rows = []
    metric = f"observable_k{k}"
    for R in sorted(sm.loc[sm["family"] == family, "range_m"].unique()):
        w = _wide(sm, family, R, metric)
        ops = [c for c in w.columns if c not in ("session_id", "uas_id", "consortium")]
        best = max(ops, key=lambda o: w[o].mean())
        shadow_c, shadow_b = 1 - w["consortium"], 1 - w[best]
        diff = shadow_b - shadow_c                                    # > 0 means cooperation reduces shadows
        est, lo, hi = stats.cluster_bootstrap_ci(diff, w["uas_id"], seed=seed)
        rows.append({"family": family, "range_m": R, "k": k, "best_operator": best, "n_sessions": len(w),
                     "mean_reduction": est, "ci_lo": lo, "ci_hi": hi,
                     "p_wilcoxon": stats.paired_wilcoxon(shadow_b, shadow_c)})
    out = pd.DataFrame(rows)
    out["p_holm"] = stats.holm(out["p_wilcoxon"])
    out["reject_h0"] = (out["p_holm"] < alpha) & (out["ci_lo"] > 0)
    return out


def h2_gap(sm: pd.DataFrame, family: str, range_ref_m: float, scale_ref_m: float, min_effect: float,
           level: int = 3, seed: int = 0) -> dict:
    """Gap = observable (k=1) − V{level} at D = scale_ref, per session, consortium, reference range."""
    w1 = _wide(sm, family, range_ref_m, "observable_k1")[["session_id", "uas_id", "consortium"]]
    wv = _wide(sm, family, range_ref_m, f"V{level}_D{int(scale_ref_m)}")[["session_id", "consortium"]]
    m = w1.merge(wv, on="session_id", suffixes=("_obs", "_ver"))
    gap = m["consortium_obs"] - m["consortium_ver"]
    est, lo, hi = stats.cluster_bootstrap_ci(gap, m["uas_id"], seed=seed)
    return {"family": family, "range_m": range_ref_m, "level": f"V{level}", "scale_m": scale_ref_m,
            "n_sessions": len(m), "mean_gap": est, "ci_lo": lo, "ci_hi": hi, "min_effect": min_effect,
            "reject_h0": lo > min_effect}


def h3_ranking(sm: pd.DataFrame, scale_ref_m: float, level: int = 3, seed: int = 0) -> pd.DataFrame:
    """Consortium minus each operator in V{level}, per (family, range); flips are reported as boundaries."""
    rows = []
    metric = f"V{level}_D{int(scale_ref_m)}"
    for (fam, R), _ in sm[sm["metric"] == metric].groupby(["family", "range_m"]):
        w = _wide(sm, fam, R, metric)
        for op in [c for c in w.columns if c not in ("session_id", "uas_id", "consortium")]:
            est, lo, hi = stats.cluster_bootstrap_ci(w["consortium"] - w[op], w["uas_id"], seed=seed)
            rows.append({"family": fam, "range_m": R, "operator": op, "mean_diff": est, "ci_lo": lo, "ci_hi": hi,
                         "holds": lo > 0})
    return pd.DataFrame(rows)
