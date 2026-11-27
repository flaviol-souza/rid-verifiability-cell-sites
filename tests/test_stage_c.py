"""Stage C: vectorized CRLB = scalar CRLB, statistics, hypotheses on synthetic tables with known answers,
characterization privacy (T17), block runner idempotency."""
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from analysis import characterization as chz
from analysis import hypotheses as hy
from analysis import stats
from analysis import verifiability as vf
from drs.channel import observe

REPO = Path(__file__).resolve().parents[1]
CH = yaml.safe_load((REPO / "experiments/configs/channel/c1_generic.yaml").read_text())


def test_fast_bounds_equal_scalar_bounds():
    rng = np.random.default_rng(1)
    rows = []
    for sid in range(200):
        n = rng.integers(1, 8)
        for _ in range(n):
            dx, dy = rng.uniform(-800, 800, 2)
            rows.append((sid, dx, dy, np.hypot(np.hypot(dx, dy), rng.uniform(-20, 60)), True))
    rows.append((999, 100.0, 0.0, 100.0, True)); rows.append((999, 200.0, 0.0, 200.0, True))   # collinear pair
    obs = pd.DataFrame(rows, columns=["sample_id", "dx_m", "dy_m", "d3_m", "heard"])
    a = vf.per_sample_bounds(obs, CH["eta"], CH["shadow_sigma_db"]).set_index("sample_id")
    b = vf.per_sample_bounds_fast(obs, CH["eta"], CH["shadow_sigma_db"]).set_index("sample_id")
    for col in ("sigma_h_v3_m", "sigma_h_v4_m", "hdop"):
        fa, fb = np.isfinite(a[col]), np.isfinite(b[col])
        assert (fa == fb).all(), col
        assert np.allclose(a.loc[fa, col], b.loc[fb, col], rtol=1e-6), col


def test_cluster_bootstrap_is_wider_than_naive_when_clusters_are_homogeneous():
    clusters = np.repeat(np.arange(10), 20)
    values = np.repeat(np.random.default_rng(0).normal(0, 1, 10), 20)
    est, lo, hi = stats.cluster_bootstrap_ci(values, clusters, n_boot=1000)
    naive_half = 1.96 * values.std(ddof=1) / np.sqrt(len(values))
    assert lo < est < hi and (hi - lo) / 2 > 2 * naive_half


def test_holm_and_wilcoxon():
    assert stats.holm([0.01, 0.04, 0.03]).tolist() == pytest.approx([0.03, 0.06, 0.06])
    assert stats.paired_wilcoxon([1, 2, 3], [1, 2, 3]) == 1.0
    assert stats.paired_wilcoxon(np.arange(30) + 1.0, np.arange(30)) < 1e-5


def _table(effect_c=0.2, gap=0.3):
    rng = np.random.default_rng(0)
    rows = []
    for s in range(40):
        uas, base = f"u{s % 8}", rng.uniform(0.4, 0.6)
        for sc, obs_k1 in (("consortium", base + effect_c), ("A", base), ("B", base - 0.1)):
            for R in (100.0, 300.0):
                for seed in (0, 1):
                    rows += [("c1", sc, R, seed, f"s{s}", uas, "observable_k1", obs_k1),
                             ("c1", sc, R, seed, f"s{s}", uas, "observable_k3", obs_k1 - 0.05),
                             ("c1", sc, R, seed, f"s{s}", uas, "V3_D100", obs_k1 - gap),
                             ("c1", sc, R, seed, f"s{s}", uas, "V4_D100", obs_k1 - gap - 0.05)]
    return pd.DataFrame(rows, columns=["family", "scenario", "range_m", "seed", "session_id", "uas_id", "metric", "value"])


def test_hypotheses_detect_known_effects_and_null():
    sm = hy.session_means(_table())
    h1 = hy.h1_cooperation(sm, "c1", k=1)
    assert h1["reject_h0"].all() and (h1["best_operator"] == "A").all()
    assert h1["mean_reduction"].iloc[0] == pytest.approx(0.2)
    h2 = hy.h2_gap(sm, "c1", 100.0, 100.0, 0.10)
    assert h2["mean_gap"] == pytest.approx(0.3) and h2["reject_h0"]
    assert not hy.h2_gap(hy.session_means(_table(gap=0.05)), "c1", 100.0, 100.0, 0.10)["reject_h0"]
    h3 = hy.h3_ranking(sm, 100.0)
    assert h3["holds"].all()
    null = hy.h1_cooperation(hy.session_means(_table(effect_c=0.0)), "c1", k=1)
    assert not null["reject_h0"].any()


def _stepped_samples():
    t0 = pd.Timestamp("2025-11-08T18:00:00Z")
    rows = []
    for i in range(40):
        rows.append(("u1", "u1_s000", t0 + pd.Timedelta(seconds=i), -23.70 + (i // 10) * 1e-4, -46.70, 30.0, 3, i % 7 == 0))
    smp = pd.DataFrame(rows, columns=["uas_id", "session_id", "t_utc", "lat", "lon", "agl_dem_m", "group_size", "in_roi"])
    smp.insert(0, "sample_id", np.arange(len(smp)))
    refs = pd.concat([smp.assign(role="pilot", lat=-23.70, lon=-46.701, agl_dem_m=6.0),
                      smp.assign(role="home", lat=-23.70, lon=-46.7012, agl_dem_m=6.5)], ignore_index=True)
    return smp, refs


def test_characterization_values_and_privacy():
    smp, refs = _stepped_samples()
    out = chz.characterize(smp, refs)
    holds = out["holds"].set_index("quantity")
    assert holds.loc["position_hold_s", "p50"] == 10.0                    # position changes every 10 s
    assert holds.loc["frac_steps_without_position_change", "p50"] == pytest.approx(36 / 39, abs=1e-4)
    for name, df in out.items():
        assert not ({"lat", "lon"} & set(df.columns)), name
    roles = out["roles"].set_index("role")
    assert roles.loc["pilot", "p50"] == 6.0 and roles.loc["drone", "rows"] == 40


def test_characterization_refuses_position_columns(monkeypatch):
    smp, refs = _stepped_samples()
    monkeypatch.setattr(chz, "group_size_table", lambda s: s[["lat", "lon"]].head(1))
    with pytest.raises(RuntimeError):
        chz.characterize(smp, refs)


def _workspace(tmp_path, range_ref=None):
    from test_stage_b import _synthetic
    smp, sites = _synthetic()
    smp["uas_id"] = smp["session_id"].str.replace("s", "u")
    (tmp_path / "data/interim").mkdir(parents=True)
    smp.to_parquet(tmp_path / "data/interim/samples.parquet", index=False)
    sites.to_parquet(tmp_path / "data/interim/sites.parquet", index=False)
    (tmp_path / "experiments/configs/channel").mkdir(parents=True)
    shutil.copy(REPO / "experiments/configs/channel/c1_generic.yaml", tmp_path / "experiments/configs/channel/")
    cfg = yaml.safe_load((REPO / "experiments/configs/reference.yaml").read_text())
    cfg["stage_b"]["range_grid_m"] = [150, 400]
    cfg["stage_b"]["range_ref_m"] = range_ref
    (tmp_path / "experiments/configs/reference.yaml").write_text(yaml.safe_dump(cfg))
    return tmp_path


def _run(script, root, *args):
    return subprocess.run([sys.executable, str(REPO / "experiments" / script), "--root", str(root), *args],
                          capture_output=True, text=True, cwd=REPO)


def test_block_runner_is_complete_and_idempotent(tmp_path):
    root = _workspace(tmp_path, range_ref=150)
    r = _run("run_blocks.py", root, "--out", "results/blockO", "--seeds", "0-1")
    assert r.returncode == 0, r.stderr
    out = root / "results/blockO"
    man = pd.read_csv(out / "manifest.csv")
    assert len(man) == 2 * 3 * 2                                         # 2 ranges × (consortium, A, B) × 2 seeds
    tbl = pd.read_parquet(out / "session_metrics.parquet")
    per_cell = tbl.groupby(["scenario", "range_m", "seed"])["session_id"].nunique()
    assert (per_cell == 2).all()                                          # every session reported in every cell
    assert not ({"lat", "lon"} & set(tbl.columns))
    mtimes = {f.name: f.stat().st_mtime_ns for f in (out / "cells").iterdir()}
    assert _run("run_blocks.py", root, "--out", "results/blockO", "--seeds", "0-1").returncode == 0
    assert mtimes == {f.name: f.stat().st_mtime_ns for f in (out / "cells").iterdir()}
    h = _run("run_hypotheses.py", root, "--blocks", "results/blockO")
    assert h.returncode == 0, h.stderr
    assert {"h1.csv", "h2.csv", "h3.csv", "truncated_cells.csv"} <= {f.name for f in (out / "hypotheses").iterdir()}


def test_hypotheses_refuse_without_reference_range(tmp_path):
    root = _workspace(tmp_path, range_ref=None)
    assert _run("run_blocks.py", root, "--out", "results/blockO", "--seeds", "0-0").returncode == 0
    assert _run("run_hypotheses.py", root, "--blocks", "results/blockO").returncode == 2


def test_characterization_runner_writes_aggregates_only(tmp_path):
    smp, refs = _stepped_samples()
    (tmp_path / "data/interim").mkdir(parents=True)
    smp.to_parquet(tmp_path / "data/interim/samples.parquet", index=False)
    refs.to_parquet(tmp_path / "data/interim/ground_refs.parquet", index=False)
    (tmp_path / "experiments/configs").mkdir(parents=True)
    shutil.copy(REPO / "experiments/configs/reference.yaml", tmp_path / "experiments/configs/")
    r = _run("run_characterization.py", tmp_path, "--out", "results/char")
    assert r.returncode == 0, r.stderr
    for f in (tmp_path / "results/char").iterdir():
        header = f.read_text().splitlines()[0].split(",")
        assert not ({"lat", "lon"} & set(header)), f.name
