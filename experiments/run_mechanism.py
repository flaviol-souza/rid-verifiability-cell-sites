"""Why are some drones never verifiable? Per-session geometry (distance to the k-th nearest site) vs session V3.

Deterministic, no channel draw: geometry comes from the drone track and the site inventory; V3 comes from the block
output (session means over seeds at the reference range). Output has no coordinates.

Usage: python experiments/run_mechanism.py --blocks results/stage_b/blockO --out results/stage_b/mechanism
"""
import argparse
import sys
from pathlib import Path

import matplotlib
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis import geometry as geo  # noqa: E402
from analysis import hypotheses as hy  # noqa: E402
from analysis import observability as ob  # noqa: E402

INK, INK_2, GRID = "#1f1f1e", "#5f5e58", "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
MARKERS = ["o", "s", "^", "D"]


def _spearman_ci(df, xcol, ycol, seed=0, n_boot=2000):
    """Spearman ρ with a cluster bootstrap CI (resampling serials)."""
    if df[xcol].nunique() < 2 or df[ycol].nunique() < 2:
        return float("nan"), float("nan"), float("nan")
    rho = float(spearmanr(df[xcol], df[ycol]).statistic)
    rng = np.random.default_rng(seed)
    groups = [g for _, g in df.groupby("uas_id", sort=True)]
    boots = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(groups), len(groups))
        b = pd.concat([groups[i] for i in pick])
        if b[xcol].nunique() > 1 and b[ycol].nunique() > 1:
            boots.append(spearmanr(b[xcol], b[ycol]).statistic)
    lo, hi = np.nanpercentile(boots, [2.5, 97.5]) if boots else (np.nan, np.nan)
    return rho, float(lo), float(hi)


def _fig_geo_vs_sim(sess, scen, metric, D, R, out, alias=None):
    from analysis.alias import label as alabel
    """Simulated V3 (with shadowing) against the geometric prediction (mean-heard links, no shadowing)."""
    fig, ax = plt.subplots(figsize=(3.5, 3.7))
    ax.plot([0, 1], [0, 1], color=INK_2, linewidth=0.8, linestyle="--", label="y = x")
    for i, sc in enumerate(scen):
        d = sess[sess["scenario"] == sc]
        ax.scatter(d[f"{metric}_geo"], d[metric], s=14, color=SERIES[i % 4], marker=MARKERS[i % 4], alpha=0.75,
                   linewidths=0, label=alabel(sc, alias))
    ax.set_xlim(-0.03, 1.03); ax.set_ylim(-0.03, 1.03); ax.set_aspect("equal")
    ax.set_xlabel(f"geometric V3 (links within R = {int(R)} m, no shadowing)", color=INK, fontsize=8)
    ax.set_ylabel(f"simulated V3 (D = {D} m)", color=INK, fontsize=8)
    ax.tick_params(colors=INK_2, labelsize=7)
    ax.grid(True, color=GRID, linewidth=0.6); ax.set_axisbelow(True)
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    h, l = ax.get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=3, fontsize=7, frameon=False)
    fig.tight_layout(rect=(0, 0.12, 1, 1))
    fig.savefig(out / "fig_geo_vs_sim.pdf", metadata={"CreationDate": None, "ModDate": None})
    fig.savefig(out / "fig_geo_vs_sim.png", dpi=200)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="experiments/configs/reference.yaml")
    ap.add_argument("--root", default=".")
    ap.add_argument("--blocks", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--scenarios", default="consortium,VIVO")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--family", default=None, help="default: the single family in the block")
    a = ap.parse_args()
    root = Path(a.root).resolve()
    cfg = yaml.safe_load((root / a.config).read_text())
    b = cfg["stage_b"]
    if b.get("range_ref_m") is None:
        print("ERROR: stage_b.range_ref_m is not set", file=sys.stderr)
        return 2
    R, D = float(b["range_ref_m"]), int(b["verif_scale_ref_m"])
    from analysis.alias import check, label as alabel, load_alias
    alias = load_alias(cfg)
    ch = yaml.safe_load((root / b["channel"]).read_text())
    d_lim = geo.crlb_range_limit_m(D, 3, ch["eta"], ch["shadow_sigma_db"])   # symmetric 3-site limit for σ_h ≤ D
    interim = root / cfg["stage_a"]["paths"]["interim_dir"]
    samples = pd.read_parquet(interim / "samples.parquet").sort_values(["session_id", "t_utc"], kind="mergesort").reset_index(drop=True)
    all_sites = pd.read_parquet(interim / "sites.parquet")
    check(alias, [o for ops in all_sites["operator"].str.split("|") for o in ops])
    cut_ring = geo.load_cut_ring(root / cfg["stage_a"]["paths"]["anatel_cut"]) \
        if cfg["stage_a"]["paths"].get("anatel_cut") else None
    w = ob.time_weights_s(samples, cfg["stage_a"]["session_gap_s"])
    sm = hy.session_means(pd.read_parquet(root / a.blocks / "session_metrics.parquet"))
    fam = a.family or sorted(sm["family"].unique())[0]
    metric = f"V3_D{D}"

    rows, summ = [], []
    for sc in a.scenarios.split(","):
        sites = all_sites if sc == "consortium" else \
            all_sites[all_sites["operator"].str.split("|").apply(lambda ops, s=sc: s in ops)]
        g = geo.session_geometry(samples, sites, all_sites, w, a.k, R, cut_ring)
        sg, ng = geo.geometric_sigma_h(samples, sites, R, ch["sniffer_height_m"], ch["eta"], ch["shadow_sigma_db"])
        ok = ((ng >= 3) & (sg <= D)).astype(float)
        vgeo = pd.Series(ok * w.to_numpy()).groupby(samples["session_id"].to_numpy()).sum() \
            / w.groupby(samples["session_id"].to_numpy()).sum().to_numpy()
        g[f"{metric}_geo"] = g["session_id"].map(vgeo)
        v = sm[(sm["family"] == fam) & (sm["scenario"] == sc) & (sm["range_m"] == R) & (sm["metric"] == metric)]
        m = g.merge(v[["session_id", "value"]].rename(columns={"value": metric}), on="session_id", how="inner")
        m.insert(0, "scenario", sc)
        rows.append(m)
        dcol = f"d{a.k}_median_m"
        rho, lo, hi = _spearman_ci(m, dcol, metric)
        near, far = m[m[dcol] <= R], m[m[dcol] > R]
        rho_g, lo_g, hi_g = _spearman_ci(m, f"{metric}_geo", metric)
        odd = m[(m[dcol] <= d_lim) & (m[metric] < 0.1)]                # close sites, yet (almost) never verifiable
        summ.append({"scenario": sc, "range_m": R, "metric": metric, "k": a.k, "n_sessions": len(m),
                     "spearman_rho": rho, "rho_ci_lo": lo, "rho_ci_hi": hi,
                     "n_near": len(near), f"mean_{metric}_near": near[metric].mean() if len(near) else np.nan,
                     "n_far": len(far), f"mean_{metric}_far": far[metric].mean() if len(far) else np.nan,
                     "sessions_mostly_edge": int((m["frac_time_inventory_edge"] > 0.5).sum()),
                     "d_limit_3sites_m": d_lim,
                     f"spearman_rho_{metric}_vs_geo": rho_g, "rho_geo_ci_lo": lo_g, "rho_geo_ci_hi": hi_g,
                     f"mean_abs_{metric}_minus_geo": float((m[metric] - m[f"{metric}_geo"]).abs().mean()),
                     "n_close_but_unverifiable": len(odd),
                     f"mean_{metric}_geo_close_but_unverifiable": odd[f"{metric}_geo"].mean() if len(odd) else np.nan})
    sess = pd.concat(rows, ignore_index=True)
    out = root / a.out
    out.mkdir(parents=True, exist_ok=True)
    sess.to_csv(out / "mechanism_sessions.csv", index=False, lineterminator="\n")
    pd.DataFrame(summ).to_csv(out / "mechanism_summary.csv", index=False, lineterminator="\n")

    scen = a.scenarios.split(",")
    fig, axes = plt.subplots(1, len(scen), figsize=(6.3, 2.7), sharey=True, sharex=True, squeeze=False)
    dcol = f"d{a.k}_median_m"
    for i, (ax, sc) in enumerate(zip(axes[0], scen)):
        d = sess[sess["scenario"] == sc]
        inner, edge = d[d["frac_time_inventory_edge"] <= 0.5], d[d["frac_time_inventory_edge"] > 0.5]
        ax.scatter(inner[dcol], inner[metric], s=14, color=SERIES[i], marker=MARKERS[i], alpha=0.8,
                   linewidths=0, label="session")
        if len(edge):
            ax.scatter(edge[dcol], edge[metric], s=18, facecolors="none", edgecolors=INK_2, marker=MARKERS[i],
                       linewidths=0.8, label="session, mostly near inventory edge")
        ax.axvline(R, color=INK_2, linewidth=0.8, linestyle="--", label=f"R = {int(R)} m")
        ax.axvline(d_lim, color=INK_2, linewidth=0.8, linestyle=":",
                   label=f"3-site CRLB limit for D = {D} m ({d_lim:.0f} m)")
        ax.set_xscale("log")
        ax.set_xticks([t for t in (25, 50, 100, 200, 500, 1000, 2000, 5000)])
        ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
        ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        ax.set_ylim(-0.03, 1.03)
        ax.set_title(alabel(sc, alias), fontsize=9, color=INK)
        if i == 0:
            ax.set_ylabel(f"V3 (D = {D} m), fraction of time", color=INK, fontsize=8)
        ax.tick_params(colors=INK_2, labelsize=7)
        ax.grid(True, color=GRID, linewidth=0.6); ax.set_axisbelow(True)
        for s_ in ("top", "right"):
            ax.spines[s_].set_visible(False)
    dmin, dmax = sess[dcol].replace(np.inf, np.nan).min(), sess[dcol].replace(np.inf, np.nan).max()
    axes[0][0].set_xlim(min(dmin, R) / 1.3, max(dmax, R) * 1.3)
    seen, hh, ll = set(), [], []
    for ax in axes[0]:
        for hi, li in zip(*ax.get_legend_handles_labels()):
            if li not in seen and li != "session":
                seen.add(li); hh.append(hi); ll.append(li)
    fig.tight_layout(rect=(0, 0.16, 1, 1))
    fig.text(0.5, 0.105, f"median distance to {a.k}rd nearest site of the scenario (m)" if a.k == 3 else
             f"median distance to site #{a.k} of the scenario (m)", color=INK, fontsize=8, ha="center")
    fig.legend(hh, ll, loc="lower center", ncol=len(ll), fontsize=7, frameon=False)
    fig.savefig(out / "fig_mechanism.pdf", metadata={"CreationDate": None, "ModDate": None})
    fig.savefig(out / "fig_mechanism.png", dpi=200)
    plt.close(fig)
    _fig_geo_vs_sim(sess, scen, metric, D, R, out, alias)
    print(pd.DataFrame(summ).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
