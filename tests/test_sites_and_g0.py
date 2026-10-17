from drs.data import stage_a


def test_sites_collapsed_and_never_clipped(workspace):
    root, cfg = workspace
    res = stage_a.run(cfg, root)
    s = res["sites"]
    assert len(s) == 3                                   # 4 records, 2 at the same location
    assert (s["n_records"].sum()) == 4
    assert ((s["lat"] == -23.80) & (s["lon"] == -46.80)).any()   # site outside RoI and domain is kept


def test_g0_passes_on_clean_synthetic_data_and_reads_criteria_from_config(workspace):
    root, cfg = workspace
    res = stage_a.run(cfg, root)
    g0 = stage_a.g0_evaluate(res["samples"], res["log"], cfg, res["domain"])
    assert g0["G0"] == "PASS", g0
    cfg["g0"]["agl_p50_range_m"] = [100.0, 120.0]        # synthetic AGL ≈ 30–50 m → must fail
    bad = stage_a.g0_evaluate(res["samples"], res["log"], cfg, res["domain"])
    assert bad["G0"] == "FAIL" and bad["failing"] == ["agl_p50_in_range"]


def test_anatel_hash_mismatch_stops(workspace):
    root, cfg = workspace
    cfg["stage_a"]["anatel_sha256"] = "0" * 64
    import pytest
    with pytest.raises(stage_a.InputHashMismatch):
        stage_a.run(cfg, root)
