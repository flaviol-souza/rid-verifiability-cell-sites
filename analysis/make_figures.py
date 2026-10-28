"""Figures for the paper, generated only from block outputs (never from typed numbers).

Every visual choice comes from analysis/figstyle.py (font, sizes, widths, colours, axes, bands, labels).
Series are named by direct labels at the left end of each line; the legend below holds only the
hatched lower-bound range. File names are unchanged (test_stage_d):
  fig_verifiability_gap_<family>   F1, main figure (paper)            full width
  fig_observability_<family>       observability per scenario (artifact; Table 3 in the paper)
  fig_shadow_reduction_<family>    H1 detail (artifact; number + CI in the text)
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.lines  # noqa: E402,F401
import matplotlib.patches  # noqa: E402,F401
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from analysis import figstyle as fs  # noqa: E402

X_PAD = (0.42, 1.12)                     # left labels: room left of the first range


def _entity_order(scenarios, alias=None):
    from analysis.alias import label
    ops = sorted((s for s in scenarios if s != "consortium"), key=lambda s: label(s, alias or {}))
    return ["consortium"] + ops


def _range_axis(ax, ranges, pad=X_PAD):
    r = sorted(set(float(v) for v in ranges))
    fs.log_distance_axis(ax, r[0] * pad[0], r[-1] * pad[1], minor=r)


def _line(ax, g, ycol, look, labels, ci="band", end="left", shift=1.0, bar_shift=None, label_x=None):
    """ci: 'band' (opaque tint), 'bars' (capped error bars, shifted by `shift` on the log axis) or None.
    Labels carry the series colour."""
    x = g["range_m"].to_numpy()
    y = g[ycol].to_numpy()
    if ci == "band":
        fs.ci_band(ax, x, g["ci_lo"].to_numpy(), g["ci_hi"].to_numpy(), look["color"])
    elif ci == "bars":
        fs.errorbars(ax, x, y, g["ci_lo"].to_numpy(), g["ci_hi"].to_numpy(), look["color"],
                     shift=shift if bar_shift is None else bar_shift)
    ax.plot(x * shift, y, color=look["color"], ls=look["ls"], lw=look["lw"], marker=look["marker"],
            markersize=3.8, markeredgewidth=0, zorder=3, clip_on=False)
    i = 0 if end == "left" else -1
    labels.append((x[i] * shift if label_x is None else label_x, y[i], look["label"], look["color"]))


def _h2_numbers(h2, family, ref_range):
    """(mean, lo, hi) of the pre-registered H2 gap at the reference range, read from hypotheses/h2.csv.
    Column names are matched loosely; None if the file or the row is not there."""
    if h2 is None or ref_range is None:
        return None
    d = h2
    if "family" in d:
        d = d[d["family"] == family]
    if "range_m" in d:
        d = d[np.isclose(d["range_m"].astype(float), float(ref_range))]
    if len(d) != 1:
        return None
    pick = lambda *names: next((float(d[n].iloc[0]) for n in names if n in d), None)  # noqa: E731
    m = pick("mean_gap", "gap_mean", "mean", "gap")
    lo, hi = pick("ci_lo", "gap_ci_lo", "lo"), pick("ci_hi", "gap_ci_hi", "hi")
    return None if None in (m, lo, hi) else (m, lo, hi)


H2_TOL = 0.01      # curves are per-flight means iff (heard - V3) at R_ref equals the H2 mean within this


def fig_verifiability_gap(summary: pd.DataFrame, truncated: list, out: Path, family: str, scale_m: float,
                          h2: pd.DataFrame = None, ref_range: float = None, trunc_from: float = None) -> Path:
    """F1 (main figure). Consortium: heard vs V3 vs V4 at scale D against the implied range.
    The band fills BETWEEN THE MEAN CURVES (heard minus V3), in the lilac of the undetectable region of
    Fig. 1 ("heard but not verifiable"). It is called "gap (H2)" only if the curves are the per-flight
    means the H2 test uses (checked against hypotheses/h2.csv); otherwise "gap", with the H2 value in
    the legend. CIs of heard and V3 are capped error bars (no fill competes with the band); V4: line only."""
    D = int(scale_m)
    fig = fs.figure(fs.WIDTH_FULL_IN, 6.6)
    ax, = fs.axes_row(fig, 1, left=1.3, right=0.25, bottom=2.15, top=0.25)
    s = summary[(summary["family"] == family) & (summary["scenario"] == "consortium")]
    obs = s[s["metric"] == "observable_k1"].sort_values("range_m")
    v3 = s[s["metric"] == f"V3_D{D}"].sort_values("range_m")
    _range_axis(ax, s["range_m"])
    m = obs[["range_m", "mean"]].merge(v3[["range_m", "mean"]], on="range_m", suffixes=("_obs", "_v3"))
    gap_color = fs.tint(fs.GAP["text"], fs.GAP["tint"])
    ax.fill_between(m["range_m"], m["mean_v3"], m["mean_obs"], color=gap_color, lw=0, zorder=1)
    labels = []
    _line(ax, obs, "mean", fs.METRIC["observable"], labels, ci="bars")
    _line(ax, v3, "mean", dict(fs.METRIC["V3"], label=rf"$V_3$, $D$ = {D} m"), labels, ci="bars",
          bar_shift=1.045)          # V3 bars just right of its markers: they never run through the V4 markers
    _line(ax, s[s["metric"] == f"V4_D{D}"].sort_values("range_m"), "mean",
          dict(fs.METRIC["V4"], label=rf"$V_4$, $D$ = {D} m"), labels, ci=None)
    # is the band the H2 quantity? (per-flight means -> difference of curves = H2 mean)
    nums = _h2_numbers(h2, family, ref_range)
    is_h2 = False
    if nums is not None and np.isclose(m["range_m"], float(ref_range)).any():
        row = m[np.isclose(m["range_m"], float(ref_range))].iloc[0]
        diff = float(row["mean_obs"] - row["mean_v3"])
        is_h2 = abs(diff - nums[0]) <= H2_TOL
        if not is_h2:
            import sys
            print(f"note: heard - V3 at R = {ref_range:g} m is {diff:.3f} on the curves but {nums[0]:.3f} in H2 "
                  "(per-flight mean): the curves are not the H2 quantity; the band is labelled 'gap'.",
                  file=sys.stderr)
    name = "gap (H2)" if is_h2 else "gap"
    # short name inside the band, between the first two ranges (where it has room)
    x0, x1 = m["range_m"].iloc[0], m["range_m"].iloc[1]
    xm = float(np.sqrt(x0 * x1))
    ym = float(np.mean([np.interp(np.log(xm), np.log(m["range_m"]), m[c]) for c in ("mean_obs", "mean_v3")]))
    ax.text(xm, ym, name, ha="center", va="center", fontsize=fs.PT["annot"], color=fs.GAP["text"], zorder=4)
    if nums is None:
        gap_label = "gap: heard $-$ $V_3$"
    elif is_h2:
        gap_label = (f"gap (H2): heard $-$ $V_3$; at $R$ = {float(ref_range):.0f} m: "
                     f"{nums[0]:.2f} [{nums[1]:.2f}, {nums[2]:.2f}]")
    else:
        gap_label = (f"gap: heard $-$ $V_3$; H2 (per-flight mean) at $R$ = {float(ref_range):.0f} m: "
                     f"{nums[0]:.2f} [{nums[1]:.2f}, {nums[2]:.2f}]")
    gap_handle = matplotlib.patches.Patch(color=gap_color, label=gap_label)
    ci_handle = matplotlib.lines.Line2D([], [], color="#444444", ls="none", marker="|", ms=8, mew=0.8,
                                        label="95% CI (heard and $V_3$)")
    fs.fraction_axis(ax, "fraction of flight time")
    ax.set_xlabel("implied range $R$ (m)")
    fs.tidy(ax)
    h = fs.shade_truncated(ax, truncated, start=trunc_from)
    fs.direct_labels(ax, labels, side="left")
    fs.legend_below(fig, [gap_handle, ci_handle, h], ncol=2)
    return _save(fig, out, f"fig_verifiability_gap_{family}")


def fig_observability(summary: pd.DataFrame, truncated: list, out: Path, family: str, ks=(1, 3), alias=None,
                      trunc_from: float = None, scale_m: float = None) -> Path:
    """Per-operator figure (F2). With scale_m: (a) three or more sites hear, |S| >= 3; (b) verifiable,
    V3 (D) -- having three sites is necessary but not sufficient. Without scale_m: |S| >= k panels.
    One line per scenario, CI bands; direct labels at the LEFT end, in the series colour (at the right
    end the lines converge). File name unchanged (test_stage_d)."""
    from analysis.alias import label
    if scale_m is not None:
        D = int(scale_m)
        panels = [("observable_k3", "(a) three or more sites hear, $|S| \\geq 3$"),
                  (f"V3_D{D}", f"(b) verifiable, $V_3$ ($D$ = {D} m)")]
    else:
        panels = [(f"observable_k{k}", f"({'abcd'[j]}) " + ("heard, " if k == 1 else "") + f"$|S| \\geq {k}$")
                  for j, k in enumerate(ks)]
    fig = fs.figure(fs.WIDTH_FULL_IN, 6.3)
    axes = fs.axes_row(fig, len(panels), left=1.3, bottom=1.65, top=0.55, gap=0.45)
    s = summary[summary["family"] == family]
    h = None
    for j, (ax, (metric, title)) in enumerate(zip(np.atleast_1d(axes), panels)):
        d = s[s["metric"] == metric]
        _range_axis(ax, d["range_m"])
        labels = []
        for sc in _entity_order(d["scenario"].unique(), alias):
            _line(ax, d[d["scenario"] == sc].sort_values("range_m"), "mean", fs.look(label(sc, alias or {})), labels)
        ax.set_title(title)
        fs.fraction_axis(ax, "fraction of flight time" if j == 0 else None)
        ax.set_xlabel("implied range $R$ (m)")
        fs.tidy(ax)
        h = fs.shade_truncated(ax, truncated, start=trunc_from)
        fs.direct_labels(ax, labels, side="left")
    fs.legend_below(fig, [h])
    return _save(fig, out, f"fig_observability_{family}")


def fig_shadow_reduction(h1: pd.DataFrame, truncated: list, out: Path, family: str, trunc_from: float = None) -> Path:
    """H1: reduction of the shadow fraction, consortium vs best single operator, with 95% CI (artifact).
    CIs as capped error bars, the two series shifted apart on the log axis so they never merge."""
    fig = fs.figure(fs.WIDTH_FULL_IN, 5.8)
    ax, = fs.axes_row(fig, 1, left=1.75, bottom=1.65, top=0.2)
    d = h1[h1["family"] == family]
    _range_axis(ax, d["range_m"])
    labels = []
    ks = sorted(d["k"].unique())
    for i, k in enumerate(ks):
        g = d[d["k"] == k].sort_values("range_m").rename(columns={"mean_reduction": "mean"})
        look = dict(fs.SHADOW_K.get(int(k), fs.SHADOW_K[3]), label=f"$|S| < {k}$")
        shift = 0.97 if i == 0 else 1.03
        _line(ax, g, "mean", look, labels, ci="bars", shift=shift,
              label_x=float(g["range_m"].min()) * 0.94)      # left of BOTH series' first bars
    ax.axhline(0, color=fs.MUTED, linewidth=0.7, zorder=2)
    ax.set_xlabel("implied range $R$ (m)")
    ax.set_ylabel("shadow-time reduction\nvs best single operator")
    fs.one_decimal(ax)
    fs.tidy(ax)
    h = fs.shade_truncated(ax, truncated, start=trunc_from)
    fs.direct_labels(ax, labels, side="left")
    ci = matplotlib.lines.Line2D([], [], color="#444444", ls="none", marker="|", ms=8, mew=0.8,
                                 label="95% CI (cluster bootstrap; series offset for legibility)")
    fs.legend_below(fig, [ci, h])
    return _save(fig, out, f"fig_shadow_reduction_{family}")


def _save(fig, out: Path, name: str) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    fs.save(fig, out / name)
    plt.close(fig)
    return out / f"{name}.pdf"
