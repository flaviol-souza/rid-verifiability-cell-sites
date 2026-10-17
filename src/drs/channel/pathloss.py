"""Log-distance mean received power. Every constant comes from the channel config (with its source)."""
import numpy as np

C_MPS = 299_792_458.0


def fspl_db(d_m, freq_hz: float):
    """Free-space path loss (dB) at distance d."""
    return 20.0 * np.log10(4.0 * np.pi * np.asarray(d_m, dtype=float) * freq_hz / C_MPS)


def pl0_db(ch: dict) -> float:
    """Reference loss at d0: free space at d0 plus a declared clutter term."""
    return float(fspl_db(ch["d0_m"], ch["freq_hz"]) + ch["clutter_db"])


def mean_rx_dbm(d_m, ch: dict):
    d = np.maximum(np.asarray(d_m, dtype=float), ch["d0_m"])
    return ch["eirp_dbm"] - pl0_db(ch) - 10.0 * ch["eta"] * np.log10(d / ch["d0_m"])


def implied_range_m(ch: dict) -> float:
    """Distance at which the mean equals the sensitivity γ (no shadowing)."""
    return float(ch["d0_m"] * 10 ** ((ch["eirp_dbm"] - pl0_db(ch) - ch["sniffer_sens_dbm"]) / (10.0 * ch["eta"])))


def tail_heard_prob(d_m: float, ch: dict) -> float:
    """P(heard) for a receiver at distance d (shadowing only). Used to check that the candidate radius r_max
    does not truncate the observer set: if P(heard at r_max) > tail_max, results in that cell are lower bounds."""
    from math import erf, sqrt
    z = (float(mean_rx_dbm(d_m, ch)) - ch["sniffer_sens_dbm"]) / ch["shadow_sigma_db"]
    return 0.5 * (1.0 + erf(z / sqrt(2.0)))


def gamma_for_range_dbm(range_m: float, ch: dict) -> float:
    """Sensitivity that gives implied range R for the channel shape (η, PL0, EIRP). Lets the design sweep R directly."""
    return float(mean_rx_dbm(range_m, ch))


def max_untruncated_range_m(ch: dict) -> float:
    """Largest implied range R for which P(heard at r_max) ≤ tail_max (inventory complete within r_max)."""
    from statistics import NormalDist
    z = NormalDist().inv_cdf(1.0 - ch["tail_max"])
    return float(ch["r_max_m"] / 10 ** (z * ch["shadow_sigma_db"] / (10.0 * ch["eta"])))
