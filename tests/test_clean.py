import pandas as pd

from drs.data import clean, stage_a


def _run(workspace):
    root, cfg = workspace
    return stage_a.run(cfg, root), cfg


def test_log_accounting_chain(workspace):
    res, _ = _run(workspace)
    log = res["log"]
    assert list(log["rule"]) == ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9"]
    assert (log["rows_before"].iloc[1:].to_numpy() == log["rows_after"].iloc[:-1].to_numpy()).all()
    assert (log["rows_before"] - log["rows_dropped"] == log["rows_after"]).all()


def test_each_rule_removes_what_it_should(workspace):
    res, _ = _run(workspace)
    d = res["log"].set_index("rule")["rows_dropped"]
    assert d["C1"] == 1 + 49                 # exact duplicate + 49 identical placeholder rows
    assert d["C2"] == 1                      # same (serial, timestamp)
    assert d["C3"] == 5                      # far serial
    assert d["C4"] == 1                      # the placeholder serial (single time, single position)
    assert d["C5"] == 1                      # sentinel altitude
    assert d["C6"] == 0 and d["C7"] == 0     # no row removed by sessionization or AGL
    assert d["C8"] == 5                      # AGL 2 m rows
    assert d["C9"] == 1                      # GNSS spike only


def test_c4_keeps_short_real_flights():
    t = pd.to_datetime(["2025-11-08T18:00:00Z", "2025-11-08T18:00:01Z"], utc=True)
    df = pd.DataFrame({"uas_id": ["x", "x"], "t_utc": t, "lat": [0, 0], "lon": [0, 0], "alt": [800, 800]})
    assert len(clean.c4_placeholders(df)) == 2


def test_c6_gap_threshold_is_strict(workspace):
    _, cfg = workspace
    gap = cfg["stage_a"]["session_gap_s"]
    t = pd.to_datetime(["2025-11-08T18:00:00Z"], utc=True)[0]
    times = [t, t + pd.Timedelta(seconds=gap), t + pd.Timedelta(seconds=2 * gap + 1)]
    df = pd.DataFrame({"uas_id": ["x"] * 3, "t_utc": times})
    s = clean.c6_sessionize(df, gap)["session_id"].tolist()
    assert s[0] == s[1] != s[2]              # exactly T_gap stays; above T_gap splits


def test_c9_removes_spike_but_keeps_following_sample(workspace):
    res, _ = _run(workspace)
    smp = res["samples"]
    a = smp[smp["session_id"].str.endswith("_s001")].sort_values("t_utc")
    assert len(a) == 9                                         # 10 samples, spike removed
    assert (a["lon"].diff().dropna() > 0).all()                # no 1 km jump left


def test_roi_tag_and_domain_filter(workspace):
    res, _ = _run(workspace)
    smp = res["samples"]
    assert smp["in_roi"].any() and (~smp["in_roi"]).any()
    assert (smp["agl_m"] > 5).all()
