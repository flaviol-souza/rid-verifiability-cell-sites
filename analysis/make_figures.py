"""Figures for the paper, generated only from block outputs (never from typed numbers).

Style: one y-axis per panel, thin lines with distinct markers and line styles (readable in greyscale), direct labels
at line ends plus a legend, recessive grid, text in ink colours (never the series colour). Categorical colours follow
the entity in a fixed order. The inventory-truncated range is shaded and labelled as a lower bound.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

INK, INK_2, GRID, SHADE = "#1f1f1e", "#5f5e58", "#e4e3df", "#f1f0ec"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]          # validated categorical slots 1–4 (light surface)
MARKERS = ["o", "s", "^", "D"]
LINESTYLES = ["-", "--", "-.", ":"]
WIDTH_IN = 6.3                                                   # SBC text width ≈ 16 cm


def _range_axis(ax, ranges):
    """Log axis with ticks at the swept ranges, plus room on the right for direct labels."""
    r = sorted(set(float(v) for v in ranges))
    ax.set_xscale("log")
    ax.set_xlim(r[0] * 0.42, r[-1] * 1.15)
    ax.set_xticks(r)
    # label every tick except those too close to a neighbour on a log axis (e.g. 750 next to 1000)
    labels = [f"{int(v)}" if i == len(r) - 1 or r[i + 1] / v > 1.4 else "" for i, v in enumerate(r)]
    ax.set_xticklabels(labels)
    ax.minorticks_off()


def _legend_below(fig, ax, ncol):
    h, l = ax.get_legend_handles_labels()
    seen, hh, ll = set(), [], []
    for hi, li in zip(h, l):
        if li not in seen:
            seen.add(li); hh.append(hi); ll.append(li)
    fig.legend(hh, ll, loc="lower center", ncol=min(ncol + 1, len(ll)), fontsize=7, frameon=False)


def _style(ax, xlabel, ylabel):
    ax.set_xlabel(xlabel, color=INK)
    ax.set_ylabel(ylabel, color=INK)
    ax.tick_params(colors=INK_2, labelsize=8)
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(INK_2)


def _shade_truncated(ax, truncated_ranges):
    """Shade the truncated ranges; the explanation goes into the legend (a patch handle), never over the data."""
    if len(truncated_ranges):
        lo = min(truncated_ranges)
        ax.axvspan(lo * 0.93, ax.get_xlim()[1], color=SHADE, zorder=0, label="lower bound (site inventory truncated)")
        ax.set_xlim(right=ax.get_xlim()[1])


def _entity_order(scenarios, alias=None):
    from analysis.alias import label
    ops = sorted((s for s in scenarios if s != "consortium"), key=lambda s: label(s, alias or {}))
    return ["consortium"] + ops


def _line(ax, x, y, lo, hi, i, label):
    ax.fill_between(x, lo, hi, color=SERIES[i], alpha=0.15, linewidth=0)
    ax.plot(x, y, color=SERIES[i], marker=MARKERS[i], markersize=4.5, linewidth=1.5, linestyle=LINESTYLES[i], label=label)
    ax._direct_labels = getattr(ax, "_direct_labels", []) + [(x[0], y[0], label)]


def _place_direct_labels(ax, min_gap=0.07):
    """Write the left-end labels, nudging them apart vertically (in axis fraction) so they never overlap."""
    items = sorted(getattr(ax, "_direct_labels", []), key=lambda t: t[1])
    if not items:
        return
    y0, y1 = ax.get_ylim()
    pos = [(v - y0) / (y1 - y0) for _, v, _ in items]
    for i in range(1, len(pos)):
        pos[i] = max(pos[i], pos[i - 1] + min_gap)
    for (x, _, label), py in zip(items, pos):
        ax.annotate(label, (x, py), xycoords=("data", "axes fraction"), xytext=(-6, 0), textcoords="offset points",
                    fontsize=7, color=INK, va="center", ha="right")


def fig_observability(summary: pd.DataFrame, truncated: list, out: Path, family: str, ks=(1, 3), alias=None) -> Path:
    """Observable fraction (|S| ≥ k) vs implied range, one panel per k, one line per scenario."""
    fig, axes = plt.subplots(1, len(ks), figsize=(WIDTH_IN, 2.5), sharey=True)
    s = summary[summary["family"] == family]
    for ax, k in zip(axes, ks):
        d = s[s["metric"] == f"observable_k{k}"]
        from analysis.alias import label
        for i, sc in enumerate(_entity_order(d["scenario"].unique(), alias)):
            g = d[d["scenario"] == sc].sort_values("range_m")
            _line(ax, g["range_m"].to_numpy(), g["mean"].to_numpy(), g["ci_lo"].to_numpy(), g["ci_hi"].to_numpy(), i,
                  label(sc, alias or {}))
        _range_axis(ax, d["range_m"])
        ax.set_title(f"|S| ≥ {k}", fontsize=9, color=INK)
        _style(ax, "implied range R (m)", "fraction of flight time" if k == ks[0] else "")
        _shade_truncated(ax, truncated)
    fig.tight_layout(rect=(0, 0.1, 1, 1))
    _legend_below(fig, axes[0], 4)
    return _save(fig, out, f"fig_observability_{family}")


def fig_verifiability_gap(summary: pd.DataFrame, truncated: list, out: Path, family: str, scale_m: float) -> Path:
    """Consortium: observable (k=1) vs V3 vs V4 at scale D, against implied range (main figure)."""
    fig, ax = plt.subplots(figsize=(WIDTH_IN * 0.7, 2.9))
    s = summary[(summary["family"] == family) & (summary["scenario"] == "consortium")]
    for i, (metric, label) in enumerate([("observable_k1", "observable (|S| ≥ 1)"),
                                         (f"V3_D{int(scale_m)}", f"V3, D = {int(scale_m)} m"),
                                         (f"V4_D{int(scale_m)}", f"V4, D = {int(scale_m)} m")]):
        g = s[s["metric"] == metric].sort_values("range_m")
        _line(ax, g["range_m"].to_numpy(), g["mean"].to_numpy(), g["ci_lo"].to_numpy(), g["ci_hi"].to_numpy(), i, label)
    _range_axis(ax, s["range_m"])
    _style(ax, "implied range R (m)", "fraction of flight time")
    _shade_truncated(ax, truncated)
    fig.tight_layout(rect=(0, 0.1, 1, 1))
    fig.tight_layout(rect=(0, 0.16, 1, 1))
    _legend_below(fig, ax, 1)
    return _save(fig, out, f"fig_verifiability_gap_{family}")


def fig_shadow_reduction(h1: pd.DataFrame, truncated: list, out: Path, family: str) -> Path:
    """H1: reduction of the shadow fraction, consortium vs best single operator, with 95% CI."""
    fig, ax = plt.subplots(figsize=(WIDTH_IN * 0.7, 2.7))
    d = h1[h1["family"] == family]
    for i, k in enumerate(sorted(d["k"].unique())):
        g = d[d["k"] == k].sort_values("range_m")
        _line(ax, g["range_m"].to_numpy(), g["mean_reduction"].to_numpy(), g["ci_lo"].to_numpy(), g["ci_hi"].to_numpy(),
              i, f"k = {k}")
    ax.axhline(0, color=INK_2, linewidth=0.8)
    _range_axis(ax, d["range_m"])
    _style(ax, "implied range R (m)", "shadow-time reduction")
    _shade_truncated(ax, truncated)
    fig.tight_layout(rect=(0, 0.1, 1, 1))
    fig.tight_layout(rect=(0, 0.12, 1, 1))
    _legend_below(fig, ax, 2)
    return _save(fig, out, f"fig_shadow_reduction_{family}")


def _save(fig, out: Path, name: str) -> Path:
    for ax in fig.axes:
        _place_direct_labels(ax)
    out.mkdir(parents=True, exist_ok=True)
    pdf = out / f"{name}.pdf"
    fig.savefig(pdf, metadata={"CreationDate": None, "ModDate": None})   # reproducible PDF bytes
    fig.savefig(out / f"{name}.png", dpi=200)
    plt.close(fig)
    return pdf
