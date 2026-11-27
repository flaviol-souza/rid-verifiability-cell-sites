"""Log-normal shadowing, AR(1) along the travelled path of each (session, site) link.

X_k = rho_k X_{k-1} + sqrt(1 - rho_k^2) * sigma * eps_k,   rho_k = exp(-Δs_k / d_corr)
d_corr = 0 gives i.i.d. shadowing. Seeds are derived from (base_seed, session_id, site_id), never from the clock.
"""
import hashlib

import numpy as np


def link_seed(base_seed: int, session_id: str, site_id: str) -> int:
    h = hashlib.sha256(f"{base_seed}|{session_id}|{site_id}".encode()).digest()
    return int.from_bytes(h[:8], "little")


def ar1_series(delta_s_m: np.ndarray, sigma_db: float, dcorr_m: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    eps = rng.standard_normal(len(delta_s_m))
    x = np.empty(len(delta_s_m))
    if len(x) == 0:
        return x
    x[0] = sigma_db * eps[0]
    if dcorr_m <= 0:
        return sigma_db * eps
    rho = np.exp(-np.asarray(delta_s_m, dtype=float) / dcorr_m)
    for k in range(1, len(x)):
        x[k] = rho[k] * x[k - 1] + np.sqrt(1.0 - rho[k] ** 2) * sigma_db * eps[k]
    return x
