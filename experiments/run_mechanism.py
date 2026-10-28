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
from analysis import figstyle as fs  # noqa: E402  one visual identity for every figure

fs.use()


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


def _scenario_look(sc, alias):
    """Paper label, colour and marker of a scenario come from its identity, never from its position
    in --scenarios (the old SERIES[i] gave Operator A the consortium's colour when run alone)."""
    from analysis.alias import label as alabel
    key = fs.scenario_key(alabel(sc, alias))
    return fs.SCENARIO[key]["label"], fs.SCENARIO[key]["color"], fs.MARKER[key]   # one spelling: "Consortium"


DIFF_CUT = 0.2      # |simulated - geometric| above this counts as a disagreement (artifact note)


def _trivial(d, metric):
    """A scenario whose flights all sit at (0, 0) agrees with the geometry by definition (no three sites)."""
    return len(d) > 0 and d[f"{metric}_geo"].abs().max() < 1e-9 and d[metric].abs().max() < 1e-9


def _geo_vs_sim_stats(d, metric):
    """Agreement figures for the artifact: Spearman, share with |diff| > DIFF_CUT split by direction
    (simulated above / below the geometric prediction), and the two extreme columns."""
    g, v = d[f"{metric}_geo"].to_numpy(float), d[metric].to_numpy(float)
    ok = np.isfinite(g) & np.isfinite(v)
    g, v = g[ok], v[ok]
    rho = float(spearmanr(g, v).statistic) if len(g) > 2 and np.ptp(g) > 0 and np.ptp(v) > 0 else float("nan")
    return dict(n=len(g), spearman_rho=rho,
                frac_abs_diff_gt=float(np.mean(np.abs(v - g) > DIFF_CUT)) if len(g) else np.nan,
                n_sim_above=int(np.sum(v - g > DIFF_CUT)), n_sim_below=int(np.sum(g - v > DIFF_CUT)),
                n_geo0_sim_high=int(np.sum((g <= 1e-9) & (v > DIFF_CUT))),
                n_geo1_sim_low=int(np.sum((g >= 1 - 1e-9) & (v < 1 - DIFF_CUT))))


def _fig_geo_vs_sim(sess, scen, metric, D, R, out, alias=None):
    """Simulated V3 (with shadowing) against the geometric prediction (no shadowing). Artifact only.
    Each point is one flight in one scenario. Spearman is given PER SCENARIO (one pooled value would
    hide the scenario where the prediction is weak); the disagreement share excludes scenarios whose
    flights all sit at (0, 0), which agree by definition, and is split by direction."""
    fig = fs.figure(fs.WIDTH_HALF_IN, 10.8)
    ax = fs.axes_cm(fig, 1.25, 4.85, 5.75, 5.75)
    ax.plot([0, 1], [0, 1], **fs.DIAGONAL, zorder=1, label="$y = x$")
    lines, keep, excluded = [], [], []
    for sc in scen:
        d = sess[sess["scenario"] == sc]
        lab, col, mk = _scenario_look(sc, alias)
        trivial = _trivial(d, metric)
        ax.scatter(d[f"{metric}_geo"], d[metric], s=11, color=col, marker=mk, alpha=0.8, linewidths=0,
                   zorder=3, label=f"{lab}: all flights at (0, 0)" if trivial else lab, clip_on=False)
        if trivial:
            excluded.append(lab)
        else:
            keep.append(sc)
            rho = _geo_vs_sim_stats(d, metric)["spearman_rho"]
            lines.append(f"{lab.replace('Operator ', 'Op. ')}: {rho:.2f}")
    st = _geo_vs_sim_stats(sess[sess["scenario"].isin(keep)], metric)
    # every number below is computed from `sess` (block outputs + geometry), never typed
    excl = f", {' and '.join(excluded)} excluded" if excluded else ""
    note = ("one point = one flight in one scenario (a flight\u2013scenario pair)\n"
            "Spearman $\\rho$: " + "; ".join(lines) + "\n"
            f"$|\\Delta| > {DIFF_CUT}$: {st['frac_abs_diff_gt']:.0%} of flight\u2013scenario pairs{excl}\n"
            f"({st['n_sim_above']} above, {st['n_sim_below']} below $y = x$; "
            f"{st['n_sim_above'] + st['n_sim_below']}/{st['n']})")
    H = fig.get_size_inches()[1] / fs.CM          # the note sits under the legend: it can never cover a point
    fig.text(0.03, 0.12 / H, note, ha="left", va="bottom", fontsize=fs.PT["annot"] - 1, linespacing=1.35)
    fs.fraction_axis(ax, f"simulated $V_3$ ($D$ = {D} m)", axis="both"); ax.set_aspect("equal")
    ax.set_xlabel(f"geometric $V_3$\n(links within $R$ = {int(R)} m, no shadowing)")
    fs.tidy(ax)
    h, l = ax.get_legend_handles_labels()
    fig.legend(h[1:] + h[:1], l[1:] + l[:1], loc="lower center", bbox_to_anchor=(0.5, 1.85 / H), ncol=2,
               frameon=False, columnspacing=0.8, handletextpad=0.2, handlelength=1.2)
    fs.save(fig, out / "fig_geo_vs_sim")
    plt.close(fig)


def _fig_mechanism(sess, scen, metric, dcol, k, R, D, d_lim, out, alias=None):
    """F3. V3 per flight against the median distance to the k-th nearest site, one panel per scenario.
    Panel titles name the scenario; the legend holds only the reference lines and the edge marker."""
    fig = fs.figure(fs.WIDTH_FULL_IN, 6.6)
    axes = [fs.axes_row(fig, len(scen), left=1.25, right=0.15, bottom=2.0, top=0.55, gap=0.3)]
    dmin, dmax = sess[dcol].replace(np.inf, np.nan).min(), sess[dcol].replace(np.inf, np.nan).max()
    lo, hi = min(dmin, d_lim, R) / 1.3, max(dmax, R) * 1.3
    narrow = len(scen) > 2                              # 4 panels of ~3.4 cm: label 100, 300, 1000 only
    for i, (ax, sc) in enumerate(zip(axes[0], scen)):
        d = sess[sess["scenario"] == sc]
        lab, col, mk = _scenario_look(sc, alias)
        inner, edge = d[d["frac_time_inventory_edge"] <= 0.5], d[d["frac_time_inventory_edge"] > 0.5]
        ax.axvline(R, **fs.RANGE_LINE, zorder=1, label=f"$R$ = {int(R)} m")
        ax.axvline(d_lim, **fs.REF_LINE, zorder=1, label=rf"$d^\star_{{3}} \approx {d_lim:.0f}$ m")
        ax.scatter(inner[dcol], inner[metric], s=11, color=col, marker=mk, alpha=0.8, linewidths=0, zorder=3,
                   clip_on=False)
        if len(edge):
            ax.scatter(edge[dcol], edge[metric], s=13, facecolors="none", edgecolors=fs.MUTED, marker="o",
                       linewidths=0.7, zorder=3, clip_on=False, label="flight mostly near the inventory edge")
        fs.log_distance_axis(ax, lo, hi, labelled=(100, 300, 1000) if narrow else fs.X_TICKS)
        fs.fraction_axis(ax, f"$V_3$ ($D$ = {D} m)" if i == 0 else None)
        ax.set_title(f"({'abcdefgh'[i]}) {lab}" if len(scen) > 1 else lab)
        fs.tidy(ax)
    nth = {1: "1st", 2: "2nd", 3: "3rd"}.get(k, f"{k}th")
    xlab = f"median distance from the drone to its {nth}-nearest site (m)"
    fs.label_strip(fig, xlab, y_cm=0.75)               # one x label for all panels, above the legend
    seen, hh = set(), []                               # reference lines + edge marker, once
    for ax in axes[0]:
        for h_, l_ in zip(*ax.get_legend_handles_labels()):
            if l_ not in seen:
                seen.add(l_); hh.append(h_)
    fs.legend_below(fig, hh)
    fs.save(fig, out / "fig_mechanism")
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="experiments/configs/reference.yaml")
    ap.add_argument("--root", default=".")
    ap.add_argument("--blocks", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--scenarios", default="consortium")
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
    alias = load_alias(cfg, root)
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
                     **{f"geo_vs_sim_{k_}": v_ for k_, v_ in _geo_vs_sim_stats(m, metric).items()},
                     f"mean_{metric}_geo_close_but_unverifiable": odd[f"{metric}_geo"].mean() if len(odd) else np.nan})
    sess = pd.concat(rows, ignore_index=True)
    out = root / a.out
    out.mkdir(parents=True, exist_ok=True)
    sess.to_csv(out / "mechanism_sessions.csv", index=False, lineterminator="\n")
    pd.DataFrame(summ).to_csv(out / "mechanism_summary.csv", index=False, lineterminator="\n")

    scen = a.scenarios.split(",")
    _fig_mechanism(sess, scen, metric, f"d{a.k}_median_m", a.k, R, D, d_lim, out, alias)
    _fig_geo_vs_sim(sess, scen, metric, D, R, out, alias)
    print(pd.DataFrame(summ).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
