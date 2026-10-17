"""Stage D: block-S variants, summary tables, figures (generated, deterministic), warnings-free bounds."""
import hashlib
import warnings

import numpy as np
import pandas as pd
import pytest

from analysis import summarize
from analysis import verifiability as vf
from test_stage_c import CH, _run, _table, _workspace


def test_summary_and_per_serial():
    s = summarize.summary_table(_table())
    row = s[(s["scenario"] == "consortium") & (s["range_m"] == 100.0) & (s["metric"] == "observable_k1")].iloc[0]
    assert row["n_sessions"] == 40 and row["n_serials"] == 8 and row["ci_lo"] <= row["mean"] <= row["ci_hi"]
    ps = summarize.per_serial_table(_table(), "c1", "consortium", 100.0, "V3_D100")
    assert ps["session_share"].sum() == pytest.approx(1.0) and len(ps) == 8


def test_fast_bounds_emit_no_warnings_and_handle_receiver_below_drone():
    obs = pd.DataFrame({"sample_id": [0, 0, 0, 1, 1], "dx_m": [0.0, 100.0, 0.0, 50.0, 50.0], "dy_m": [0.0, 0.0, 100.0, 0.0, 0.0],
                        "d3_m": [30.0, 104.0, 104.0, 60.0, 60.0], "heard": True})
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        pb = vf.per_sample_bounds_fast(obs, CH["eta"], CH["shadow_sigma_db"]).set_index("sample_id")
    assert np.isfinite(pb.loc[0, "sigma_h_v3_m"]) and pb.loc[1, "sigma_h_v3_m"] == float("inf")


def test_block_variants_and_summary_figures(tmp_path):
    root = _workspace(tmp_path, range_ref=150)
    smp = pd.read_parquet(root / "data/interim/samples.parquet")
    smp["group_size"] = np.where(smp["session_id"] == "s2", 1, 3)
    smp["agl_anchor"] = np.where(smp["session_id"] == "s2", "none", "home")
    smp["agl_dem_m"] = smp["agl_m"] + 6.0
    smp.to_parquet(root / "data/interim/samples.parquet", index=False)
    for args, n in ((["--sample-filter", "exclude_group1"], 1), (["--sample-filter", "exclude_unanchored"], 1),
                    (["--agl", "dem"], 2)):
        out = f"results/S_{'_'.join(args).strip('-')}"
        r = _run("run_blocks.py", root, "--out", out, "--seeds", "0-0", *args)
        assert r.returncode == 0, r.stderr
        assert pd.read_parquet(root / out / "session_metrics.parquet")["session_id"].nunique() == n
    assert _run("run_blocks.py", root, "--out", "results/blockO", "--seeds", "0-1").returncode == 0
    assert _run("run_hypotheses.py", root, "--blocks", "results/blockO").returncode == 0
    r = _run("run_summary.py", root, "--blocks", "results/blockO")
    assert r.returncode == 0, r.stderr
    figs = root / "results/blockO/figures"
    names = {f.name for f in figs.iterdir()}
    assert {"fig_observability_c1_generic.pdf", "fig_verifiability_gap_c1_generic.pdf",
            "fig_shadow_reduction_c1_generic.pdf"} <= names
    h1 = hashlib.sha256((figs / "fig_verifiability_gap_c1_generic.pdf").read_bytes()).hexdigest()
    assert _run("run_summary.py", root, "--blocks", "results/blockO").returncode == 0
    assert hashlib.sha256((figs / "fig_verifiability_gap_c1_generic.pdf").read_bytes()).hexdigest() == h1
    summ = pd.read_csv(root / "results/blockO/summary/summary.csv")
    assert not ({"lat", "lon"} & set(summ.columns))
