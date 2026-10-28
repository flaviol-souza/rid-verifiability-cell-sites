"""One visual identity for every figure of the paper (analysis/figstyle.py).

Every figure script does
    from analysis import figstyle as fs
    fs.use()
    fig = plt.figure(figsize=(fs.WIDTH_FULL_IN, h))       # final size: never rescale in LaTeX
    ax.plot(x, y, **fs.style("Operator A"))               # colour + dash + width of Operator A
    fs.save(fig, out / "fig_name")                        # vector PDF (+ PNG preview)
and never writes a colour, a font size or a figure width by hand.

The standard (agreed 27 Oct 2026):
  * font: TeX Gyre Termes (Times-like, as the SBC text), math in STIX; 8-9 pt at final size;
  * width: 15 cm (full) or 7.3 cm (half); LaTeX includes the PDF at natural size (no width=);
  * layout: constrained, so nothing is clipped and the size stays exact (no bbox="tight");
  * series are named by DIRECT labels on the curves; the legend below holds only what is not a
    series (hatched lower-bound range, reference lines R and d*_3, marker variants);
  * CI bands: opaque tints at 15 % (overlaps never add up to a darker band);
  * fractions: y from 0 to 1 with a tick at 0; ranges/distances: log x with ticks 100 200 300 500 1000;
  * notation as in the text: $V_3$, $V_4$, $|S| \\geq 1$, "Consortium".
Colours: Okabe-Ito (colour-blind safe); every scenario also has its own dash and marker (greyscale).
style.mplstyle, when present, is loaded first; the typography below is applied on top of it.
"""
from pathlib import Path
import shutil
import subprocess
import warnings

import matplotlib.colors as mc
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

STYLE_FILE = Path(__file__).with_name("style.mplstyle")

# ---- size and type -------------------------------------------------------------------------------
CM = 1 / 2.54
WIDTH_FULL_IN = 15.0 * CM
WIDTH_HALF_IN = 7.3 * CM
PT = dict(text=8, tick=8, label=8.5, title=9, legend=8, annot=8)
FONT = "TeX Gyre Termes"

# ---- scenarios: one colour, dash and marker each, fixed for the whole paper ----------------------
SCENARIO = {
    "Consortium": dict(color="#000000", ls="-",                    lw=1.4, label="Consortium"),
    "A":          dict(color="#0072B2", ls=(0, (5, 2)),            lw=1.1, label="Operator A"),
    "B":          dict(color="#D55E00", ls=(0, (3, 1.5, 1, 1.5)),  lw=1.1, label="Operator B"),
    "C":          dict(color="#009E73", ls=(0, (1, 1.3)),          lw=1.3, label="Operator C"),
}
ORDER = ("Consortium", "A", "B", "C")
MARKER = {"Consortium": "o", "A": "s", "B": "D", "C": "P"}     # never "^": triangles are cell sites

# ---- map layers: colours no scenario uses -----------------------------------------------------------
EVENT_ZONE = dict(color="#333333", lw=1.3, ls="-", label="event zone")
#   dark solid outline: the lilac/purple family is reserved for "heard but not verifiable"
DOMAIN = dict(color="#555555", lw=0.8, ls=(0, (4, 3)), label="analysis domain")
SITE = dict(marker="^", facecolor="white", edgecolor="black", linewidths=0.6)
SITE_OTHER = dict(marker="^", facecolor="none", edgecolor="#b5b5b5", linewidths=0.45)
FLIGHT_CMAP = "Blues"                                                          # flight time

# ---- shared reference elements: the same thing looks the same in every figure ---------------------
FRAME_COLOR = "#bbbbbb"
REF_LINE = dict(color="#444444", lw=0.8, ls=(0, (1, 1.5)))        # d*_3
RANGE_LINE = dict(color="#9a9a9a", lw=0.8, ls=(0, (5, 4)))        # implied range R
DIAGONAL = dict(color="#8c8c8c", lw=0.6, ls="-")                  # y = x
MUTED = "#8c8c8c"
TRUNCATED = dict(facecolor="none", edgecolor="#cfcfcf", hatch="////", lw=0)
TRUNC_LABEL = "lower bound (site inventory truncated)"
GRID = dict(color="#dddddd", lw=0.3)
CI_TINT = 0.15
X_TICKS = (100, 200, 300, 500, 1000)                              # every log range / distance axis

# ---- consortium-only plots: the series are metrics, not scenarios ---------------------------------
METRIC = {
    "observable": dict(color="#8c8c8c", ls="-",          lw=1.3, marker="o", label=r"heard (observable, $|S| \geq 1$)"),
    "V3":         dict(color="#000000", ls="-",          lw=1.4, marker="s", label=r"$V_3$"),
    "V4":         dict(color="#000000", ls=(0, (4, 2)),  lw=1.1, marker="D", label=r"$V_4$"),
}
SHADOW_K = {
    1: dict(color="#000000", ls="-",         lw=1.4, marker="o"),
    3: dict(color="#8c8c8c", ls=(0, (4, 2)), lw=1.2, marker="s"),
}

# ---- concept figure (teaser) and the "heard but not verifiable" accent -----------------------------
TEASER = dict(
    lie="#A94B7F",                 # declared position, the lie, the "fails" verdict
    ok=REF_LINE["color"],
    undetectable_fill="#eed4e1",   # lilac = tint(lie, 0.22): SAME colour as the gap band of the F1 figure
    undetectable_edge="#A94B7F",   # edge and hatch in the lie's purple
    link="#8c8c8c",
    range_R="#9a9a9a",
)
GAP = dict(text=TEASER["lie"], tint=0.22)   # "heard but not verifiable": F1 gap band = Fig. 1 region
ERRORBAR = dict(elinewidth=0.7, capsize=2.2, capthick=0.7)   # CIs where a band would fight another fill


def tint(color, amount):
    """Opaque mix of `color` with white (amount 0 = white, 1 = colour): bands never darken each other."""
    r, g, b = mc.to_rgb(color)
    return (1 - amount * (1 - r), 1 - amount * (1 - g), 1 - amount * (1 - b))


# ---- typography ---------------------------------------------------------------------------------------
def _ensure_font():
    """Make TeX Gyre Termes available: installed font, or the copy shipped with TeX (kpsewhich)."""
    names = {f.name for f in fm.fontManager.ttflist}
    if FONT in names:
        return True
    kpse = shutil.which("kpsewhich")
    if kpse:
        for f in ("texgyretermes-regular.otf", "texgyretermes-bold.otf", "texgyretermes-italic.otf",
                  "texgyretermes-bolditalic.otf"):
            p = subprocess.run([kpse, f], capture_output=True, text=True).stdout.strip()
            if p:
                fm.fontManager.addfont(p)
    if FONT in {f.name for f in fm.fontManager.ttflist}:
        return True
    warnings.warn(f"{FONT} not found (install it, or TeX with tex-gyre); falling back to a Times-like font")
    return False


def paper_rc():
    return {
        "font.family": "serif", "font.serif": [FONT, "Nimbus Roman", "Times New Roman", "STIXGeneral"],
        "mathtext.fontset": "stix",
        "font.size": PT["text"], "axes.labelsize": PT["label"], "axes.titlesize": PT["title"],
        "xtick.labelsize": PT["tick"], "ytick.labelsize": PT["tick"], "legend.fontsize": PT["legend"],
        "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
        "xtick.major.size": 3, "ytick.major.size": 3, "xtick.minor.size": 1.8,
        "axes.titlepad": 4, "legend.frameon": False, "legend.handlelength": 2.4,
        "figure.constrained_layout.h_pad": 0.03, "figure.constrained_layout.w_pad": 0.03,
        "savefig.bbox": "standard",          # keep the final size; constrained layout prevents clipping
        "pdf.fonttype": 42, "hatch.linewidth": 0.45,
    }


def use():
    """style.mplstyle (if any) first, then the paper typography on top -- the identity lives here."""
    if STYLE_FILE.exists():
        plt.style.use(STYLE_FILE)
    _ensure_font()
    plt.rcParams.update(paper_rc())


# ---- helpers shared by the figure scripts ---------------------------------------------------------------
def figure(width_in, height_cm):
    """A figure at its final size with NO layout engine: axes are placed in centimetres (axes_row), so
    the result does not depend on the matplotlib version or on any rc file loaded elsewhere."""
    use()                                   # re-apply: another module may have reset the style since import
    return plt.figure(figsize=(width_in, height_cm * CM), layout="none")


def axes_cm(fig, left, bottom, width, height, **kw):
    W, H = fig.get_size_inches() / CM
    return fig.add_axes([left / W, bottom / H, width / W, height / H], **kw)


def axes_row(fig, n, left=1.3, right=0.2, bottom=1.6, top=0.25, gap=0.4, sharey=True):
    """n panels side by side, margins in cm. With sharey, only the first panel keeps y tick labels."""
    W, H = fig.get_size_inches() / CM
    w = (W - left - right - gap * (n - 1)) / n
    h = H - bottom - top
    axes = []
    for i in range(n):
        ax = axes_cm(fig, left + i * (w + gap), bottom, w, h, sharey=axes[0] if (sharey and axes) else None)
        if sharey and i:
            ax.tick_params(labelleft=False)
        axes.append(ax)
    return axes


def subplots(*args, **kw):
    """Kept for compatibility; prefer figure() + axes_row()."""
    use()
    kw.setdefault("layout", "constrained")
    return plt.subplots(*args, **kw)


def scenario_key(name):
    """'Consortium' / 'A' / 'Operator A' / 'consortium' -> key of SCENARIO (raises if unknown)."""
    n = str(name).strip()
    if n.lower().startswith("consortium"):
        return "Consortium"
    last = n.split()[-1]
    if last in SCENARIO:
        return last
    raise KeyError(f"no style for scenario {name!r}: pass its paper label (alias), e.g. 'Operator A'")


def style(name, **override):
    """Line kwargs for a scenario, e.g. ax.step(x, y, **style('Operator B'))."""
    return {**SCENARIO[scenario_key(name)], **override}


def look(name):
    """Line + marker kwargs of a scenario (for lines with markers)."""
    k = scenario_key(name)
    st = SCENARIO[k]
    return dict(color=st["color"], ls=st["ls"], lw=st["lw"], marker=MARKER[k], label=st["label"])


def tidy(ax, grid=True):
    """Light grid behind, no top/right spines."""
    if grid:
        ax.grid(True, **GRID); ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)


FRACTION_TICKS = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


def fraction_axis(ax, label=None, axis="y"):
    """0 to 1 with a tick at 0, one decimal everywhere ("0.0" ... "1.0")."""
    for a in (("x", "y") if axis == "both" else (axis,)):
        getattr(ax, f"set_{a}lim")(0, 1)
        getattr(ax, f"set_{a}ticks")(FRACTION_TICKS)
        getattr(ax, f"set_{a}ticklabels")([f"{t:.1f}" for t in FRACTION_TICKS])
    if label:
        ax.set_ylabel(label)


def one_decimal(ax, axis="y"):
    """Tick labels with one decimal, as on the fraction axes."""
    from matplotlib.ticker import FormatStrFormatter
    getattr(ax, f"{axis}axis").set_major_formatter(FormatStrFormatter("%.1f"))


def errorbars(ax, x, y, lo, hi, color, shift=1.0, zorder=2.5):
    """95% CI as capped error bars at each x; `shift` (e.g. 0.97 / 1.03) offsets series on a log axis."""
    import numpy as np
    x, y, lo, hi = (np.asarray(v, float) for v in (x, y, lo, hi))
    ax.errorbar(x * shift, y, yerr=[np.clip(y - lo, 0, None), np.clip(hi - y, 0, None)], fmt="none",
                ecolor=color, zorder=zorder, clip_on=False, **ERRORBAR)


RSTAR_KEY = "inv_max_untruncated_range_at_configured_r_max_m"     # key in the generated numbers.tex


def read_macro(tex_path, key=RSTAR_KEY):
    """Numeric value stored under `key` in a generated numbers.tex, whatever the defining command:
    \\newcommand{\\key}{232}, a key-value store such as \\ds-style definitions ({key}{232}), or key = 232.
    The key is matched exactly (word boundaries, case-insensitive). None if absent."""
    import re
    p = Path(tex_path)
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8")
    pat = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(key) + r"(?!\w)\}?\s*(?:\{\s*|=\s*)([-+]?\d[\d,]*\.?\d*)", re.I)
    m = pat.search(text)
    return float(m.group(1).replace(",", "")) if m else None


def r_star(r_max_m, eta, sigma_db, p=0.01):
    """Largest implied range whose results are complete (BM-32): Pr{heard at r_max} = p.
    Pr{heard | d} = Q(10 eta log10(d/R) / sigma)  =>  R* = r_max 10^(-Q^-1(p) sigma / (10 eta))."""
    from scipy.stats import norm
    return r_max_m * 10 ** (-norm.isf(p) * sigma_db / (10 * eta))


def log_distance_axis(ax, lo, hi, minor=(), labelled=X_TICKS):
    """Log x with the paper's ticks; values in `minor` (e.g. 750) get an unlabelled tick."""
    ax.set_xscale("log")
    ax.set_xlim(lo, hi)
    ticks = [t for t in X_TICKS if lo <= t <= hi]
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(t) if t in labelled else "" for t in ticks])
    ax.set_xticks([m for m in minor if lo <= m <= hi and m not in ticks], minor=True)
    ax.xaxis.set_minor_formatter(plt.NullFormatter())


def ci_band(ax, x, lo, hi, color, zorder=1):
    ax.fill_between(x, lo, hi, color=tint(color, CI_TINT), lw=0, zorder=zorder)


def ci_outline(ax, x, lo, hi, color, zorder=2):
    """CI as two thin dotted edges: overlapping intervals stay readable (no fill hides another)."""
    for y in (lo, hi):
        ax.plot(x, y, color=color, lw=0.6, ls=(0, (1, 1.2)), zorder=zorder, clip_on=False)


def shade_truncated(ax, truncated_ranges, start=None, factor=0.93):
    """Hatch the swept ranges whose values are lower bounds (decision of 28 Oct 2026: the hatch marks
    the POINTS that are lower bounds, i.e. it starts just before the first truncated range). The legend
    label is built from the same list, so figure and legend cannot disagree; R* itself goes in the
    caption (inv_max_untruncated_range_at_configured_r_max_m). `start` overrides the left edge.
    Returns the legend handle or None."""
    if not len(truncated_ranges):
        return None
    right = ax.get_xlim()[1]
    first = min(truncated_ranges)
    x0 = start if start is not None else first * factor
    label = f"values for $R \\geq {first:g}$ m are lower bounds (site inventory truncated)"
    h = ax.axvspan(x0, right, **TRUNCATED, zorder=0, label=label)
    ax.set_xlim(right=right)
    return h


def direct_labels(ax, items, side="left", min_gap=0.075, offset_pt=5):
    """items = [(x, y, text)] or [(x, y, text, colour)]: series names at the line ends, nudged apart
    (axis fraction), each in its series colour so stacked names stay attributable."""
    items = [tuple(it) + ("black",) if len(it) == 3 else tuple(it) for it in items]
    return _direct_labels(ax, items, side, min_gap, offset_pt)


def _direct_labels(ax, items, side, min_gap, offset_pt):
    """items = [(x, y, text)]: write series names at the line ends, nudged apart (axis fraction).
    Text in ink, never in the series colour."""
    items = sorted(items, key=lambda t: t[1])
    if not items:
        return
    y0, y1 = ax.get_ylim()
    pos = [(it[1] - y0) / (y1 - y0) for it in items]
    for i in range(1, len(pos)):
        pos[i] = max(pos[i], pos[i - 1] + min_gap)
    if pos[-1] > 1.0:                                  # pushed off the top: shift the stack down
        shift = pos[-1] - 1.0
        pos = [p - shift for p in pos]
    if pos[0] < 0.04:                                  # never sitting on the x axis
        shift = 0.04 - pos[0]
        pos = [p + shift for p in pos]
    dx = -offset_pt if side == "left" else offset_pt
    for (x, _, text, color), py in zip(items, pos):
        ax.annotate(text, (x, py), xycoords=("data", "axes fraction"), xytext=(dx, 0), textcoords="offset points",
                    fontsize=PT["annot"], va="center", ha="right" if side == "left" else "left",
                    color=color, annotation_clip=False)


def legend_below(fig, handles, ncol=None, y_cm=0.08):
    """Legend for non-series elements only, in the bottom strip of the figure (y_cm from the edge)."""
    handles = [h for h in handles if h is not None]
    if handles:
        H = fig.get_size_inches()[1] / CM
        fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, y_cm / H), ncol=ncol or len(handles),
                   frameon=False, columnspacing=1.6, handletextpad=0.5, borderaxespad=0, borderpad=0)


def label_strip(fig, text, y_cm, x_frac=0.5):
    """An axis title shared by several panels, at a fixed height (cm) from the bottom."""
    H = fig.get_size_inches()[1] / CM
    fig.text(x_frac, y_cm / H, text, ha="center", va="bottom", fontsize=PT["label"])


def save(fig, path_stem):
    """Vector PDF for the paper (deterministic bytes) + 300 dpi PNG preview."""
    fig.savefig(f"{path_stem}.pdf", metadata={"CreationDate": None, "ModDate": None})
    fig.savefig(f"{path_stem}.png", dpi=300)
