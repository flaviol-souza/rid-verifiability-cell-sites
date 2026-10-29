"""Stage F: common map frame across scenarios, inventory-edge flag, geometric mechanism of verifiability."""
import numpy as np
import pandas as pd
import pytest

from analysis import geometry as geo
from test_stage_c import _run, _workspace


def test_kth_site_distance_closed_form():
    sx, sy = [0.0, 100.0, 0.0, 300.0], [0.0, 0.0, 200.0, 0.0]
    d = geo.kth_site_distance_m(sx, sy, [0.0], [0.0], 3)
    assert d[0] == pytest.approx(200.0)
    assert np.isinf(geo.kth_site_distance_m(sx[:2], sy[:2], [0.0], [0.0], 3)[0])


def test_bbox_edge_distance_sign():
    sx, sy = [0.0, 1000.0], [0.0, 1000.0]
    d = geo.bbox_edge_distance_m(sx, sy, [500.0, 100.0, -50.0], [500.0, 500.0, 500.0])
    assert list(d) == [500.0, 100.0, -50.0]


def test_weighted_median():
    assert geo.weighted_median([1.0, 2.0, 10.0], [1.0, 1.0, 5.0]) == 10.0
    assert geo.weighted_median([3.0, 1.0, 2.0], [1.0, 1.0, 1.0]) == 2.0


def test_map_frame_is_common_across_scenarios(tmp_path):
    root = _workspace(tmp_path, range_ref=150)
    for sc, out in (("consortium", "results/map"), ("A", "results/map_A")):
        r = _run("run_map.py", root, "--out", out, "--seeds", "0-0", "--min-time-s", "0", "--scenario", sc)
        assert r.returncode == 0, r.stderr
    c = pd.read_csv(root / "results/map/cells.csv")
    a = pd.read_csv(root / "results/map_A/cells.csv")
    assert c[["ix", "iy", "time_s"]].equals(a[["ix", "iy", "time_s"]])      # same grid, same time per cell
    assert "inventory_edge" in c.columns and c["inventory_edge"].dtype == bool


def test_mechanism_runner(tmp_path):
    root = _workspace(tmp_path, range_ref=150)
    assert _run("run_blocks.py", root, "--out", "results/blockO", "--seeds", "0-1").returncode == 0
    r = _run("run_mechanism.py", root, "--blocks", "results/blockO", "--out", "results/mech", "--scenarios", "consortium,A")
    assert r.returncode == 0, r.stderr
    s = pd.read_csv(root / "results/mech/mechanism_sessions.csv")
    assert not ({"lat", "lon"} & set(s.columns))
    assert set(s["scenario"]) == {"consortium", "A"} and s["session_id"].nunique() == 2
    assert (s["d3_median_m"] > 0).all() and s["frac_time_inventory_edge"].between(0, 1).all()
    # consortium has a superset of sites → its 3rd-nearest site is never farther than operator A's
    p = s.pivot(index="session_id", columns="scenario", values="d3_median_m")
    assert (p["consortium"] <= p["A"] + 1e-9).all()
    assert (root / "results/mech/fig_mechanism.pdf").exists()


def test_crlb_range_limit_matches_symmetric_geometry():
    from analysis import verifiability as vf
    eta, sig, D = 2.2, 6.0, 100.0
    d = geo.crlb_range_limit_m(D, 3, eta, sig)
    ang = np.radians([90.0, 210.0, 330.0])
    dxy = np.c_[d * np.cos(ang), d * np.sin(ang)]
    assert vf.crlb_h_m(dxy, np.full(3, d), eta, sig) == pytest.approx(D, rel=1e-9)
    assert d == pytest.approx(137.9, abs=0.1)


def test_geometric_sigma_uses_only_sites_within_range():
    smp = pd.DataFrame({"sample_id": [0], "lat": [-23.70], "lon": [-46.70], "agl_m": [30.0]})
    m = 1 / 111_195.0
    sites = pd.DataFrame({"lat": [-23.70 + 100 * m, -23.70 - 50 * m, -23.70 - 50 * m, -23.70 + 900 * m],
                          "lon": [-46.70, -46.70 + 87 * m / np.cos(np.radians(23.7)),
                                  -46.70 - 87 * m / np.cos(np.radians(23.7)), -46.70]})
    s, n = geo.geometric_sigma_h(smp, sites, 200.0, 30.0, 2.2, 6.0)
    assert n[0] == 3 and np.isfinite(s[0]) and s[0] < 100.0
    s2, n2 = geo.geometric_sigma_h(smp, sites.iloc[:2], 200.0, 30.0, 2.2, 6.0)
    assert n2[0] == 2


def test_mechanism_summary_has_geometric_columns_and_map_modes(tmp_path):
    root = _workspace(tmp_path, range_ref=150)
    assert _run("run_blocks.py", root, "--out", "results/blockO", "--seeds", "0-0").returncode == 0
    r = _run("run_mechanism.py", root, "--blocks", "results/blockO", "--out", "results/mech", "--scenarios", "consortium")
    assert r.returncode == 0, r.stderr
    summ = pd.read_csv(root / "results/mech/mechanism_summary.csv")
    assert {"d_limit_3sites_m", "spearman_rho_V3_D100_vs_geo", "n_close_but_unverifiable",
            "distant_flights_v3_R1000_upper_below_0_1_fraction", "distant_flights_min_external_sites"} <= set(summ.columns)
    sess = pd.read_csv(root / "results/mech/mechanism_sessions.csv")
    assert {"v3_R1000_lower", "v3_R1000_upper", "n_star_R1000"} <= set(sess.columns)
    assert (sess["v3_R1000_lower"] <= sess["v3_R1000_upper"]).all()
    assert sess["V3_D100_geo"].between(0, 1).all()
    for extra in ([], ["--full-extent"]):
        r = _run("run_map.py", root, "--out", "results/m", "--seeds", "0-0", "--min-time-s", "0", *extra)
        assert r.returncode == 0, r.stderr


def test_hull_edge_distance():
    sx, sy = [0.0, 1000.0, 0.0, 1000.0, 500.0], [0.0, 0.0, 1000.0, 1000.0, 500.0]
    d = geo.hull_edge_distance_m(sx, sy, [500.0, 100.0, -50.0], [500.0, 500.0, 500.0])
    assert d == pytest.approx([500.0, 100.0, -50.0])
    # triangle: bbox corner (900, 900) is outside the hull although inside the bbox
    tx, ty = [0.0, 1000.0, 0.0], [0.0, 0.0, 1000.0]
    assert geo.hull_edge_distance_m(tx, ty, [900.0], [900.0])[0] < 0 < geo.bbox_edge_distance_m(tx, ty, [900.0], [900.0])[0]


def test_map_writes_inventory_margin_and_mechanism_geo_figure(tmp_path):
    import json
    root = _workspace(tmp_path, range_ref=150)
    r = _run("run_map.py", root, "--out", "results/m", "--seeds", "0-0", "--min-time-s", "0")
    assert r.returncode == 0, r.stderr
    m = json.loads((root / "results/m/inventory_margin.json").read_text())
    assert {"min_sample_distance_to_site_hull_m", "time_share_within_R_of_inventory_edge",
            "max_untruncated_range_if_r_max_raised_m"} <= set(m) and m["basis"] == "site_hull"
    # with a documented cut polygon in the config, the margin is measured against it
    import yaml
    cut = {"type": "Polygon", "coordinates": [[[-46.72, -23.72], [-46.68, -23.72], [-46.68, -23.66], [-46.72, -23.66],
                                               [-46.72, -23.72]]]}
    (root / "data/external/anatel").mkdir(parents=True, exist_ok=True)
    (root / "data/external/anatel/cut_polygon.geojson").write_text(json.dumps(cut))
    cfgp = root / "experiments/configs/reference.yaml"
    cfg = yaml.safe_load(cfgp.read_text()); cfg["stage_a"]["paths"]["anatel_cut"] = "data/external/anatel/cut_polygon.geojson"
    cfgp.write_text(yaml.safe_dump(cfg))
    assert _run("run_map.py", root, "--out", "results/m2", "--seeds", "0-0", "--min-time-s", "0").returncode == 0
    m2 = json.loads((root / "results/m2/inventory_margin.json").read_text())
    assert m2["basis"] == "cut_polygon" and m2["min_sample_distance_to_inventory_edge_m"] > 1500
    assert "inventory_margin_m" in pd.read_csv(root / "results/m2/cells.csv").columns
    assert "hull_margin_m" in pd.read_csv(root / "results/m/cells.csv").columns
    assert _run("run_blocks.py", root, "--out", "results/blockO", "--seeds", "0-0").returncode == 0
    assert _run("run_mechanism.py", root, "--blocks", "results/blockO", "--out", "results/mech",
                "--scenarios", "consortium,A").returncode == 0
    assert (root / "results/mech/fig_geo_vs_sim.pdf").exists()


def test_polygon_edge_distance_matches_closed_form():
    px, py = [0.0, 1000.0, 1000.0, 0.0], [0.0, 0.0, 800.0, 800.0]
    d = geo.polygon_edge_distance_m(px, py, [500.0, 100.0, -50.0, 500.0], [400.0, 400.0, 400.0, 900.0])
    assert d == pytest.approx([400.0, 100.0, -50.0, -100.0])
    # closed ring gives the same answer
    assert geo.polygon_edge_distance_m(px + [0.0], py + [0.0], [500.0], [400.0])[0] == pytest.approx(400.0)


def test_inventory_edge_uses_cut_polygon_and_rejects_inconsistent_cut(tmp_path):
    import json
    sites = pd.DataFrame({"lat": [-23.70, -23.71, -23.69], "lon": [-46.70, -46.69, -46.69]})
    ring = np.array([[-46.72, -23.72], [-46.68, -23.72], [-46.68, -23.68], [-46.72, -23.68], [-46.72, -23.72]])
    p = tmp_path / "cut.geojson"
    p.write_text(json.dumps({"type": "Polygon", "coordinates": [ring.tolist()]}))
    r = geo.load_cut_ring(p)
    d, basis = geo.inventory_edge_distance_m(sites, [0.0], [0.0], -23.70, -46.70, r)
    assert basis == "cut_polygon" and d[0] > 1500
    assert geo.inventory_edge_distance_m(sites, [0.0], [0.0], -23.70, -46.70, None)[1] == "site_hull"
    bad = ring.copy(); bad[1:3, 0] = -46.695                       # cut too narrow: a site falls outside
    with pytest.raises(ValueError):
        geo.inventory_edge_distance_m(sites, [0.0], [0.0], -23.70, -46.70, bad)
    assert geo.load_cut_ring(tmp_path / "missing.geojson") is None


def test_freeze_numbers_are_sourced_and_reproducible(tmp_path):
    import hashlib
    root = _workspace(tmp_path, range_ref=150)
    assert _run("run_blocks.py", root, "--out", "results/blockO", "--seeds", "0-1").returncode == 0
    assert _run("run_hypotheses.py", root, "--blocks", "results/blockO").returncode == 0
    assert _run("run_summary.py", root, "--blocks", "results/blockO").returncode == 0
    assert _run("run_blocks.py", root, "--out", "results/S1", "--seeds", "0-0").returncode == 0
    assert _run("run_hypotheses.py", root, "--blocks", "results/S1").returncode == 0
    assert _run("run_mechanism.py", root, "--blocks", "results/blockO", "--out", "results/mech",
                "--scenarios", "consortium,A,B").returncode == 0
    assert _run("run_map.py", root, "--out", "results/map", "--seeds", "0-0", "--min-time-s", "0").returncode == 0
    import yaml
    cfgp = root / "experiments/configs/reference.yaml"
    cfg = yaml.safe_load(cfgp.read_text())
    r0 = _run("run_freeze.py", root, "--blockO", "results/blockO", "--mechanism", "results/mech", "--map", "results/map",
              "--out", "results/freeze0")
    assert r0.returncode != 0 and "de-identified" in r0.stderr
    cfg["presentation"] = {"operator_alias": {"A": "A", "B": "B"}}
    cfgp.write_text(yaml.safe_dump(cfg))
    args = ("--map-scenario", "consortium=results/map",
            "--blockO", "results/blockO", "--mechanism", "results/mech", "--map", "results/map", "--out", "results/freeze",
            "--family", "c1_generic", "--blockS", "s1=results/S1")
    r = _run("run_freeze.py", root, *args)
    assert r.returncode == 0, r.stderr
    n = pd.read_csv(root / "results/freeze/numbers.csv")
    assert n["key"].is_unique and n["source"].notna().all() and len(n) > 40
    assert {"obs_k1_consortium_R150", "obs_k1_opA_R150", "h2_V3_mean_gap", "h2S_s1_gap", "map_blind_share_consortium",
            "mech_sim_above_geo_consortium", "inv_min_sample_distance_to_inventory_edge_m"} <= set(n["key"])
    assert not n["key"].str.contains(r"_A_|_B_").any()
    pubmd = (root / "results/freeze/results_freeze_public.md").read_text()
    assert "scenario=Operator A" in pubmd and "scenario=A," not in pubmd
    assert (root / "results/freeze/numbers_public.csv").exists()
    tex = (root / "results/freeze/numbers.tex").read_text()
    assert "\\csname ds@h2_V3_mean_gap\\endcsname" in tex
    h = hashlib.sha256(tex.encode()).hexdigest()
    assert _run("run_freeze.py", root, *args).returncode == 0
    assert hashlib.sha256((root / "results/freeze/numbers.tex").read_bytes()).hexdigest() == h
