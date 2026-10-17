"""RQ3: upper bound on RSS-based position verifiability.

Cramér–Rao bound on the horizontal error from the RSS of the observer set, with log-normal shadowing:
  g_i = (10 η / (σ ln 10)) · u_i / d_i,   u_i = horizontal vector receiver→drone divided by d_i (3D distance)
  J = Σ g_i g_iᵀ,   σ_h = sqrt(tr(J⁻¹))
(the horizontal gradient of 10 η log10 d_i is (10 η / ln 10) Δ_xy / d_i²; form as in Patwari et al. 2003, ⚠ Eq. 10).
V4 (unknown transmit power): each row is augmented with 1/σ and σ_h comes from the 2×2 position block of J⁻¹.
HDOP (unweighted horizontal unit vectors) is a descriptor only.
"""
import numpy as np


def crlb_h_m(dxy_m: np.ndarray, d3_m: np.ndarray, eta: float, sigma_db: float, unknown_power: bool = False) -> float:
    """dxy_m: (n, 2) horizontal vectors receiver→drone; d3_m: (n,) 3D distances. Returns inf if not identifiable."""
    dxy, d3 = np.asarray(dxy_m, dtype=float).reshape(-1, 2), np.asarray(d3_m, dtype=float)
    n_min = 3 if unknown_power else 2
    if len(d3) < n_min:
        return float("inf")
    b = 10.0 * eta / (sigma_db * np.log(10.0))
    g = b * dxy / (d3[:, None] ** 2)
    if unknown_power:
        g = np.hstack([g, np.full((len(d3), 1), 1.0 / sigma_db)])
    J = g.T @ g
    if np.linalg.cond(J) > 1e12:
        return float("inf")
    cov = np.linalg.inv(J)
    return float(np.sqrt(cov[0, 0] + cov[1, 1]))


def hdop(dxy_m: np.ndarray) -> float:
    dxy = np.asarray(dxy_m, dtype=float).reshape(-1, 2)
    if len(dxy) < 2:
        return float("inf")
    u = dxy / np.linalg.norm(dxy, axis=1, keepdims=True)
    G = u.T @ u
    if np.linalg.cond(G) > 1e12:
        return float("inf")
    c = np.linalg.inv(G)
    return float(np.sqrt(c[0, 0] + c[1, 1]))


def verifiable(n_obs: int, sigma_h_m: float, level: int, scale_m: float) -> bool:
    """level 3 → V3 (known power), level 4 → V4 (unknown power)."""
    return n_obs >= level and sigma_h_m <= scale_m


def per_sample_bounds(obs, eta: float, sigma_db: float):
    """One row per sample with ≥ 1 heard site: n_obs, σ_h (V3, known power), σ_h (V4, unknown power), HDOP."""
    import pandas as pd
    heard = obs[obs["heard"]]
    rows = []
    for sid, g in heard.groupby("sample_id", sort=True):
        dxy = g[["dx_m", "dy_m"]].to_numpy()
        d3 = g["d3_m"].to_numpy()
        rows.append((sid, len(g), crlb_h_m(dxy, d3, eta, sigma_db, False),
                     crlb_h_m(dxy, d3, eta, sigma_db, True), hdop(dxy)))
    return pd.DataFrame(rows, columns=["sample_id", "n_obs", "sigma_h_v3_m", "sigma_h_v4_m", "hdop"])
