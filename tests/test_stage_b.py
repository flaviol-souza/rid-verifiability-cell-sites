"""Stage B/C conformance tests: T3 (channel), T4 (shadowing), T5 (determinism), T6 (censoring), T15 (CRLB, HDOP),
plus observability metrics on synthetic cases. Parameters are read from config, never repeated as constants."""
import hashlib
import io
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from analysis import observability as ob
from analysis import verifiability as vf
from drs.channel import observe, pathloss, shadowing

REPO = Path(__file__).resolve().parents[1]
CH = yaml.safe_load((REPO / "experiments/configs/channel/c1_generic.yaml").read_text())


def _synthetic():
    lat0, lon0 = -23.70, -46.70
    sites = pd.DataFrame({"site_id": ["site_000", "site_001", "site_002", "site_003", "site_004"],
                          "lat": [lat0, lat0 + 0.003, lat0 - 0.003, lat0, lat0 + 0.02],   # last one beyond r_max
                          "lon": [lon0 + 0.003, lon0, lon0, lon0 - 0.003, lon0],
                          "operator": ["A", "A", "B", "B", "A"]})
    t = pd.Timestamp("2025-11-08T18:00:00Z")
    rows = []
    for k in range(30):
        rows.append(("s1", t + pd.Timedelta(seconds=k), lat0 + k * 1e-5, lon0, 40.0))
    for k in range(10):
        rows.append(("s2", t + pd.Timedelta(seconds=100 + k), lat0, lon0 + k * 1e-5, 25.0))
    smp = pd.DataFrame(rows, columns=["session_id", "t_utc", "lat", "lon", "agl_m"])
    smp.insert(0, "sample_id", np.arange(len(smp)))
    return smp, sites


# ---------- T3: channel equation ----------
def test_T3_mean_matches_closed_form_with_config_constants():
    d = np.array([1.0, 10.0, 100.0, 1000.0])
    fspl_d0 = 20 * np.log10(4 * np.pi * CH["d0_m"] * CH["freq_hz"] / 299_792_458.0)
    expected = CH["eirp_dbm"] - (fspl_d0 + CH["clutter_db"]) - 10 * CH["eta"] * np.log10(d / CH["d0_m"])
    assert np.allclose(pathloss.mean_rx_dbm(d, CH), expected)
    R = pathloss.implied_range_m(CH)
    assert pathloss.mean_rx_dbm(R, CH) == pytest.approx(CH["sniffer_sens_dbm"], abs=1e-9)
    assert pathloss.tail_heard_prob(R, CH) == pytest.approx(0.5, abs=1e-9)


# ---------- T4: shadowing statistics ----------
def test_T4_shadowing_sigma_and_autocorrelation():
    sigma, dcorr = CH["shadow_sigma_db"], 50.0
    ds = np.full(200_000, 5.0)                                   # 5 m per step → lag dcorr = 10 steps
    x = shadowing.ar1_series(ds, sigma, dcorr, seed=123)
    assert np.std(x) == pytest.approx(sigma, rel=0.02)
    lag = int(dcorr / 5.0)
    r = np.corrcoef(x[:-lag], x[lag:])[0, 1]
    assert r == pytest.approx(np.exp(-1), abs=0.02)
    iid = shadowing.ar1_series(ds[:50_000], sigma, 0.0, seed=1)
    assert abs(np.corrcoef(iid[:-1], iid[1:])[0, 1]) < 0.02


def test_link_seed_is_stable_and_distinct():
    a = shadowing.link_seed(0, "s1", "site_000")
    assert a == shadowing.link_seed(0, "s1", "site_000")
    assert a != shadowing.link_seed(1, "s1", "site_000") != shadowing.link_seed(0, "s1", "site_001")


# ---------- T5: determinism ----------
def _parquet_bytes(df):
    buf = io.BytesIO(); df.to_parquet(buf, index=False); return buf.getvalue()


def test_T5_observations_byte_identical_for_same_seed():
    smp, sites = _synthetic()
    a = observe.observe(smp, sites, CH, seed=7)
    b = observe.observe(smp.sample(frac=1, random_state=3), sites.iloc[::-1], CH, seed=7)   # input order must not matter
    assert hashlib.sha256(_parquet_bytes(a)).digest() == hashlib.sha256(_parquet_bytes(b)).digest()
    c = observe.observe(smp, sites, CH, seed=8)
    assert not a["rssi_dbm"].equals(c["rssi_dbm"])


# ---------- T6: censoring recorded ----------
def test_T6_every_candidate_pair_present_heard_or_not():
    smp, sites = _synthetic()
    ch = dict(CH, sniffer_sens_dbm=-76.0)                      # sites at ~330 m: mean ≈ γ → mixed heard/unheard
    obs = observe.observe(smp, sites, ch, seed=0)
    assert set(obs["site_id"]) == {"site_000", "site_001", "site_002", "site_003"}   # site_004 beyond r_max
    assert len(obs) == len(smp) * 4
    assert (~obs["heard"]).any() and obs["heard"].any()
    assert obs["heard"].equals(obs["rssi_dbm"] >= ch["sniffer_sens_dbm"])


def test_distances_are_3d_with_receiver_height():
    smp, sites = _synthetic()
    obs = observe.observe(smp, sites, CH, seed=0)
    dz = smp.set_index("sample_id").loc[obs["sample_id"], "agl_m"].to_numpy() - CH["sniffer_height_m"]
    assert np.allclose(obs["d3_m"], np.hypot(obs["dh_m"], dz))
    assert np.allclose(obs["dh_m"], np.hypot(obs["dx_m"], obs["dy_m"]))


# ---------- T15: CRLB and HDOP ----------
def _square(d):
    return np.array([[d, 0.0], [0.0, d], [-d, 0.0], [0.0, -d]])


def test_T15_square_closed_form_and_scaling():
    eta, sigma, d = CH["eta"], CH["shadow_sigma_db"], 200.0
    b = 10 * eta / (sigma * np.log(10))
    s = vf.crlb_h_m(_square(d), np.full(4, d), eta, sigma)
    assert s == pytest.approx(d / b, rel=1e-9)                   # J = (b²/d²)·diag(2,2) → σ_h = d / b
    assert vf.crlb_h_m(_square(2 * d), np.full(4, 2 * d), eta, sigma) == pytest.approx(2 * s)
    assert vf.crlb_h_m(_square(d), np.full(4, d), eta, 2 * sigma) == pytest.approx(2 * s)
    assert vf.hdop(_square(d)) == pytest.approx(1.0)


def test_T15_unknown_power_never_helps_and_collinear_is_singular():
    eta, sigma = CH["eta"], CH["shadow_sigma_db"]
    sym = vf.crlb_h_m(_square(200.0), np.full(4, 200.0), eta, sigma, unknown_power=True)
    assert sym == pytest.approx(vf.crlb_h_m(_square(200.0), np.full(4, 200.0), eta, sigma), rel=1e-9)
    asym = np.array([[100.0, 0.0], [0.0, 300.0], [-500.0, 0.0], [0.0, -150.0]])
    d3 = np.linalg.norm(asym, axis=1)
    assert vf.crlb_h_m(asym, d3, eta, sigma, True) > vf.crlb_h_m(asym, d3, eta, sigma, False)
    line = np.array([[100.0, 0.0], [200.0, 0.0], [-300.0, 0.0]])
    assert vf.crlb_h_m(line, np.abs(line[:, 0]), eta, sigma) == float("inf")
    assert vf.crlb_h_m(_square(100.0)[:1], np.array([100.0]), eta, sigma) == float("inf")


def test_verifiable_levels():
    assert vf.verifiable(3, 80.0, 3, 100.0) and not vf.verifiable(3, 80.0, 4, 100.0)
    assert not vf.verifiable(5, 120.0, 3, 100.0)


# ---------- observability metrics ----------
def test_time_weights_and_fractions():
    t = pd.to_datetime(["2025-11-08T18:00:00Z", "2025-11-08T18:00:01Z", "2025-11-08T18:00:03Z",
                        "2025-11-08T18:10:00Z"], utc=True)
    smp = pd.DataFrame({"sample_id": range(4), "session_id": ["a", "a", "a", "b"], "t_utc": t})
    w = ob.time_weights_s(smp, gap_cap_s=60.0)
    assert w.tolist() == [1.0, 2.0, 1.5, 1.0]                   # last of 'a' = median(1, 2); 'b' alone → 1 s
    n = pd.Series([0, 3, 1, 2])
    f = ob.observable_fraction(smp, n, w, k=1)
    assert f["a"] == pytest.approx(3.5 / 4.5) and f["b"] == 1.0


def test_shadow_windows_respect_session_boundaries():
    t = pd.date_range("2025-11-08T18:00:00Z", periods=6, freq="1s")
    smp = pd.DataFrame({"sample_id": range(6), "session_id": ["a", "a", "a", "b", "b", "b"], "t_utc": t})
    ok = pd.Series([True, False, False, False, True, False])
    w = pd.Series(1.0, index=smp.index)
    win = ob.shadow_windows(smp, ok, w)
    assert win["n_samples"].tolist() == [2, 1, 1] and win["session_id"].tolist() == ["a", "b", "b"]


def test_per_sample_bounds_end_to_end():
    smp, sites = _synthetic()
    obs = observe.observe(smp, sites, CH, seed=0)
    pb = vf.per_sample_bounds(obs, CH["eta"], CH["shadow_sigma_db"])
    assert (pb["sigma_h_v4_m"] >= pb["sigma_h_v3_m"] - 1e-9).all()
    n = ob.n_observers(smp, obs)
    assert n.max() <= 4 and (pb.set_index("sample_id")["n_obs"] == n[n > 0].values).all()


def test_pilot_runner_on_synthetic_workspace(tmp_path):
    import shutil, subprocess, sys
    smp, sites = _synthetic()
    (tmp_path / "data/interim").mkdir(parents=True)
    smp.to_parquet(tmp_path / "data/interim/samples.parquet", index=False)
    sites.to_parquet(tmp_path / "data/interim/sites.parquet", index=False)
    (tmp_path / "experiments/configs/channel").mkdir(parents=True)
    shutil.copy(REPO / "experiments/configs/channel/c1_generic.yaml", tmp_path / "experiments/configs/channel/")
    shutil.copy(REPO / "experiments/configs/reference.yaml", tmp_path / "experiments/configs/")
    r = subprocess.run([sys.executable, str(REPO / "experiments/run_stage_b.py"), "--root", str(tmp_path), "--gamma", "-76"],
                       capture_output=True, text=True, cwd=REPO)
    assert r.returncode == 0, r.stderr
    prov = yaml.safe_load(next((tmp_path / "results/stage_b/pilot").iterdir()).joinpath("provenance.yaml").read_text())
    s = prov["summary"]
    assert s["observable_k1"] >= s["observable_k3"] >= s["V3_D200"] >= s["V3_D50"]
    assert s["V3_D100"] >= s["V4_D100"]
    assert b"\r" not in next((tmp_path / "results/stage_b/pilot").iterdir()).joinpath("provenance.yaml").read_bytes()


def test_range_parametrization_and_truncation_limit():
    for R in (100.0, 300.0, 1000.0):
        ch = dict(CH, sniffer_sens_dbm=pathloss.gamma_for_range_dbm(R, CH))
        assert pathloss.implied_range_m(ch) == pytest.approx(R, rel=1e-9)
    Rmax = pathloss.max_untruncated_range_m(CH)
    ch = dict(CH, sniffer_sens_dbm=pathloss.gamma_for_range_dbm(Rmax, CH))
    assert pathloss.tail_heard_prob(CH["r_max_m"], ch) == pytest.approx(CH["tail_max"], rel=1e-6)
