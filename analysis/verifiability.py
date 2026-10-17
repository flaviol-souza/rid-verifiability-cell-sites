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


def per_sample_bounds_fast(obs, eta: float, sigma_db: float, cond_max: float = 1e12):
    """Vectorized equivalent of per_sample_bounds (same definitions; tested against it).
    J components are summed per sample; V4 uses the Schur complement of the power term."""
    import pandas as pd
    h = obs[obs["heard"]]
    with np.errstate(divide="ignore", invalid="ignore"):
        return _fast_bounds(h, eta, sigma_db, cond_max)


def _fast_bounds(h, eta, sigma_db, cond_max):
    import pandas as pd
    b = 10.0 * eta / (sigma_db * np.log(10.0))
    d2 = h["d3_m"].to_numpy() ** 2
    gx = b * h["dx_m"].to_numpy() / d2
    gy = b * h["dy_m"].to_numpy() / d2
    gp = np.full(len(h), 1.0 / sigma_db)
    dh = np.hypot(h["dx_m"].to_numpy(), h["dy_m"].to_numpy())
    safe = dh > 0                                   # receiver right under the drone: no horizontal direction
    ux = np.where(safe, h["dx_m"].to_numpy() / np.where(safe, dh, 1.0), 0.0)
    uy = np.where(safe, h["dy_m"].to_numpy() / np.where(safe, dh, 1.0), 0.0)
    df = pd.DataFrame({"sample_id": h["sample_id"].to_numpy(), "n": 1,
                       "xx": gx * gx, "xy": gx * gy, "yy": gy * gy, "xp": gx * gp, "yp": gy * gp, "pp": gp * gp,
                       "uxx": ux * ux, "uxy": ux * uy, "uyy": uy * uy})
    s = df.groupby("sample_id", sort=True).sum()

    def trace_inv_2x2(a, c, d):          # [[a, c], [c, d]]
        det = a * d - c * c
        tr = a + d
        ok = (det > 0) & (tr > 0) & (tr * tr / np.where(det > 0, det, np.inf) < cond_max)
        return np.where(ok, np.sqrt(np.where(ok, tr / np.where(det > 0, det, 1.0), np.inf)), np.inf)

    v3 = trace_inv_2x2(s["xx"], s["xy"], s["yy"])
    v3 = np.where(s["n"] >= 2, v3, np.inf)
    a = s["xx"] - s["xp"] ** 2 / s["pp"]
    c = s["xy"] - s["xp"] * s["yp"] / s["pp"]
    d = s["yy"] - s["yp"] ** 2 / s["pp"]
    v4 = np.where(s["n"] >= 3, trace_inv_2x2(a, c, d), np.inf)
    hd = np.where(s["n"] >= 2, trace_inv_2x2(s["uxx"], s["uxy"], s["uyy"]), np.inf)
    return pd.DataFrame({"sample_id": s.index.to_numpy(), "n_obs": s["n"].to_numpy(),
                         "sigma_h_v3_m": np.asarray(v3, dtype=float), "sigma_h_v4_m": np.asarray(v4, dtype=float),
                         "hdop": np.asarray(hd, dtype=float)})
