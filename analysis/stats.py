"""Statistics fixed before seeing the data (methods.md): cluster bootstrap by serial, paired Wilcoxon, Holm."""
import numpy as np
import pandas as pd
from scipy import stats as st


def cluster_bootstrap_ci(values: pd.Series, clusters: pd.Series, n_boot: int = 2000, alpha: float = 0.05,
                         seed: int = 0, stat=np.mean) -> tuple[float, float, float]:
    """CI of stat(values) resampling whole clusters (serials) with replacement. values: one per session."""
    v = pd.Series(np.asarray(values, dtype=float))
    c = pd.Series(np.asarray(clusters))
    groups = [v[c == k].to_numpy() for k in pd.unique(c)]
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    for i in range(n_boot):
        pick = rng.integers(0, len(groups), len(groups))
        boots[i] = stat(np.concatenate([groups[j] for j in pick]))
    lo, hi = np.quantile(boots, [alpha / 2, 1 - alpha / 2])
    return float(stat(v.to_numpy())), float(lo), float(hi)


def paired_wilcoxon(x, y) -> float:
    """Two-sided p-value of the Wilcoxon signed-rank test on paired samples (zero differences dropped)."""
    d = np.asarray(x, dtype=float) - np.asarray(y, dtype=float)
    d = d[d != 0]
    if len(d) == 0:
        return 1.0
    return float(st.wilcoxon(d).pvalue)


def holm(pvals) -> np.ndarray:
    """Holm step-down adjusted p-values (same order as input)."""
    p = np.asarray(pvals, dtype=float)
    order = np.argsort(p)
    m = len(p)
    adj = np.empty(m)
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (m - rank) * p[idx])
        adj[idx] = min(1.0, running)
    return adj
