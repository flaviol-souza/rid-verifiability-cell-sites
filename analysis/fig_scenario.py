"""Scenario figure for Section 4 (Data): where the drones flew, where the cell sites are, and how far
the third-nearest site is -- the quantity that the range limit d*_3 turns into verifiability (F2, F3).

Writes TWO figures (default; --only consortium|operators for one):
  fig_scenario.pdf            consortium map + d_(3) CDF (panels a, b below)
  fig_scenario_operators.pdf  one map per operator, side by side
Consortium figure:
  (a) map: flight time per hexagonal cell + ALL licensed sites with one marker (consortium view).
      No per-operator map: research.md / BM-39 (no map that lets a reader count sites per operator).
  (b) time-weighted CDF of the distance from the drone to its 3rd-nearest site, consortium and
      Operators A/B/C, with d*_3 marked. Its value at d*_3 is the fraction of flight time in which
      three sites lie within the symmetric range limit. It is a geometric INDICATOR, not a bound on V3:
      two very close sites plus a far third can satisfy V3 with d_(3) > d*_3, and one-sided sites can
      fail it with d_(3) < d*_3.
Operator figure: each operator's sites in black, the others faint grey (--no-others hides them).
It lets a reader count sites per operator: BM-39, lead author's call.

Layers of the map (bottom to top):
  1. flight time per hexagonal cell (w_t = min(t+ - t, T_gap), Eq. 5), log colour scale; cells seen by
     fewer than MIN_DRONES distinct drones are dropped (privacy by construction, rule 6);
  2. analysis domain (dashed) and event zone / RoI (solid);
  3. every licensed site with ONE marker; 4. scale bar.

Inputs (git-ignored interim files from Stage A; drone positions only, never pilot or home):
  --samples data/interim/samples.parquet   --sites data/interim/sites.parquet
  --roi data/external/roi/roi.geojson       --domain data/external/roi/domain.geojson
Run:  python3 fig_scenario.py --samples ... --sites ... --roi ... --domain ... --out paper/figures
Demo: python3 fig_scenario.py --demo --out .   (synthetic data, watermarked; never use in the paper)
Also writes fig_scenario_numbers.csv (fraction of time with d_(3) <= d*_3, pooled and drone-weighted)
so the text can quote the numbers through macros instead of reading them off the plot.
"""
import argparse, json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm, ListedColormap
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator, FixedFormatter, NullLocator
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # repo root: analysis.* importable
try:
    from analysis.figstyle import use as use_style, SCENARIO, EVENT_ZONE, DOMAIN, SITE, SITE_OTHER, FLIGHT_CMAP
except ImportError:                                               # script copied next to figstyle.py
    from figstyle import use as use_style, SCENARIO, EVENT_ZONE, DOMAIN, SITE, SITE_OTHER, FLIGHT_CMAP

COLS = dict(drone="uas_id", session="session_id", t="t_utc", lat="lat", lon="lon", in_domain="in_domain",
            agl="agl_m", site_lat="lat", site_lon="lon", operator="operator")  # operator holds A/B/C
# ---- parameters: read these from the pipeline config when it exposes them (rule: no repeated constants)
T_GAP_S = 60.0
ETA, SIGMA_DB, D_M = 2.2, 6.0, 100.0   # channel C1 and reference resolution
H_RX_M = 30.0                          # receiver height (assumption A5)
HEX_M = 75.0                           # hexagon size; coarse enough not to draw individual tracks
MIN_DRONES = 2                         # drop cells seen by a single drone
EPSG_LOCAL = 31983                     # SIRGAS 2000 / UTM 23S; origin = RoI centroid
MAP_PAD_M = 600                        # map margin around the flight-time support
OPS = ("A", "B", "C")
FRAME = "domain"                       # set by --frame
MAP_FRAME_PAD_M = 250                  # margin around the analysis domain (frame "domain")
B = 10 * ETA / (SIGMA_DB * np.log(10))
D3_STAR = D_M * B * np.sqrt(3) / 2     # range limit for three sites (= 137.9 m at the reference)

use_style()
CMAP = ListedColormap(plt.get_cmap(FLIGHT_CMAP)(np.linspace(0.25, 1.0, 256)))  # lowest cells stay visible on white


# ------------------------------------------------------------------------------------------ data
def to_local(lat, lon, origin):
    from pyproj import Transformer
    tr = Transformer.from_crs(4326, EPSG_LOCAL, always_xy=True)
    x, y = tr.transform(np.asarray(lon), np.asarray(lat))
    return np.asarray(x) - origin[0], np.asarray(y) - origin[1]


def time_weights(df):
    """w_t = min(t+ - t, T_gap), last sample of a flight = the flight's median interval (Eq. 5).
    Returned in the ORDER OF df (the old fallback returned them sorted, misaligned with x, y)."""
    try:
        from analysis.observability import time_weights_s   # prefer the pipeline's implementation
    except ImportError:                                      # only a missing module falls back
        time_weights_s = None
    if time_weights_s is not None:
        return np.asarray(time_weights_s(df, T_GAP_S))
    g = df.groupby(COLS["session"])[COLS["t"]]
    nxt = df.sort_values([COLS["session"], COLS["t"]]).groupby(COLS["session"])[COLS["t"]].shift(-1)
    dt = (nxt - df[COLS["t"]].loc[nxt.index]).reindex(df.index)
    med = g.transform(lambda s: s.sort_values().diff().median())
    return np.minimum(dt.fillna(med), T_GAP_S).to_numpy()


def ring_xy(geojson_path, origin):
    g = json.load(open(geojson_path))
    geom = g["features"][0]["geometry"] if "features" in g else g
    coords = geom["coordinates"][0] if geom["type"] == "Polygon" else geom["coordinates"][0][0]
    lon, lat = np.array(coords).T
    return to_local(lat, lon, origin)


def third_nearest(fx, fy, dz, sx, sy):
    """3-D distance from each sample to its 3rd-nearest site (inf if fewer than 3 sites)."""
    if len(sx) < 3:
        return np.full(len(fx), np.inf)
    d2 = (fx[:, None] - sx[None]) ** 2 + (fy[:, None] - sy[None]) ** 2
    return np.sqrt(np.partition(d2, 2, axis=1)[:, 2] + dz ** 2)


def weighted_cdf(x, w):
    o = np.argsort(x)
    return x[o], np.cumsum(w[o]) / w.sum()


def drone_weights(w, drone):
    """Every drone counts the same: w / (total time of that drone)."""
    _, inv = np.unique(drone, return_inverse=True)
    return w / np.bincount(inv, weights=w)[inv]


# ------------------------------------------------------------------------------------------ drawing
def flight_hexbin(ax, fx, fy, fw, fdrone, extent):
    gs = int(round((extent[1] - extent[0]) / HEX_M))
    hb = ax.hexbin(fx, fy, C=fw, reduce_C_function=np.sum, gridsize=gs, extent=extent, mincnt=1,
                   linewidths=0, cmap=CMAP, zorder=1)
    if MIN_DRONES > 1:
        # same grid, same points => same cells in the same order: distinct drones per cell, exactly
        codes = np.unique(fdrone, return_inverse=True)[1].astype(float)
        hd = ax.hexbin(fx, fy, C=codes, reduce_C_function=lambda v: len(np.unique(v)), gridsize=gs,
                       extent=extent, mincnt=1)
        ndr = np.asarray(hd.get_array()); hd.remove()
        vals = np.asarray(hb.get_array(), float)
        vals[ndr < MIN_DRONES] = np.nan
        hb.set_array(np.ma.masked_invalid(vals))
    v = hb.get_array().compressed()
    hb.set_norm(LogNorm(vmin=max(v.min(), 1.0), vmax=v.max()))
    return hb


def scalebar(ax, extent, length=None):
    if length is None:
        w = extent[1] - extent[0]
        length = 500 if w < 5000 else 1000 if w < 10000 else 2000
    x0 = extent[0] + 0.05 * (extent[1] - extent[0]); y0 = extent[2] + 0.05 * (extent[3] - extent[2])
    ax.plot([x0, x0 + length], [y0, y0], color="black", lw=1.6, solid_capstyle="butt", zorder=7)
    ax.text(x0 + length + 0.02 * (extent[1] - extent[0]), y0, f"{length} m", ha="left", va="center",
            fontsize=7, zorder=7)


def draw_map(ax, fx, fy, fw, fd, sx, sy, roi, domain, extent, others=None, scale=True):
    """others = (x, y) of the sites NOT in this panel, drawn faint so the consortium stays visible."""
    hb = flight_hexbin(ax, fx, fy, fw, fd, extent)
    ax.plot(*domain, **{**DOMAIN, "label": None}, zorder=2)
    ax.plot(*roi, **{**EVENT_ZONE, "label": None}, zorder=3)

    def inside(x, y):
        return (x >= extent[0]) & (x <= extent[1]) & (y >= extent[2]) & (y <= extent[3])
    if others is not None:
        ox, oy = others; k = inside(ox, oy)
        ax.scatter(ox[k], oy[k], s=9, **SITE_OTHER, zorder=4, clip_on=False)
    k = inside(sx, sy)
    ax.scatter(sx[k], sy[k], s=13, **{**SITE, "facecolor": "white" if others is None else "black"},
               zorder=5, clip_on=False)
    ax.set_xlim(extent[:2]); ax.set_ylim(extent[2:]); ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_color("#bbbbbb")
    if scale:
        scalebar(ax, extent)
    return hb


def colorbar(fig, hb, cax):
    cb = fig.colorbar(hb, cax=cax)
    cb.set_label(f"flight time per {HEX_M:.0f} m cell", fontsize=7, labelpad=2)
    lab = {1: "1 s", 10: "10 s", 60: "1 min", 600: "10 min", 3600: "1 h"}
    ticks = [t for t in lab if hb.norm.vmin <= t <= hb.norm.vmax]
    cb.ax.yaxis.set_major_locator(FixedLocator(ticks)); cb.ax.yaxis.set_minor_locator(NullLocator())
    cb.ax.yaxis.set_major_formatter(FixedFormatter([lab[t] for t in ticks]))
    cb.ax.tick_params(labelsize=6.5, length=2, width=0.5); cb.outline.set_linewidth(0.5)
    return cb


def map_legend_handles(domain_clipped=False):
    dom = {**DOMAIN, "label": "analysis domain" + (" (continues beyond frame)" if domain_clipped else "")}
    return [Line2D([], [], **dom), Line2D([], [], **EVENT_ZONE),
            Line2D([], [], marker="^", ls="none", ms=4.5, mfc="white", mec="black", mew=0.6, label="cell site")]


def map_extent(fx, fy, roi, domain, frame="domain"):
    """Square frame. 'domain': the whole analysis domain fits, plus MAP_FRAME_PAD_M.
    'flights': tight around flights and event zone (the domain may then be cut; the legend says so).
    Returns (extent, domain_clipped)."""
    if frame == "domain":
        xs, ys = np.asarray(domain[0]), np.asarray(domain[1]); pad = MAP_FRAME_PAD_M
        lo_x, hi_x, lo_y, hi_y = xs.min(), xs.max(), ys.min(), ys.max()
    else:
        xs, ys = np.r_[fx, roi[0]], np.r_[fy, roi[1]]; pad = MAP_PAD_M
        (lo_x, hi_x), (lo_y, hi_y) = np.percentile(xs, [0.5, 99.5]), np.percentile(ys, [0.5, 99.5])
    cx, cy = (lo_x + hi_x) / 2, (lo_y + hi_y) / 2
    half = max(hi_x - lo_x, hi_y - lo_y) / 2 + pad
    ext = (cx - half, cx + half, cy - half, cy + half)
    dx, dy = np.asarray(domain[0]), np.asarray(domain[1])
    clipped = bool(dx.min() < ext[0] or dx.max() > ext[1] or dy.min() < ext[2] or dy.max() > ext[3])
    return ext, clipped


# ------------------------------------------------------------------------------------------ figures
def draw_cdf(ax, fx, fy, fw, fd, dz, sx, sy, ops, xmax=1000.0, legend_outside=False):
    rows, wd = [], drone_weights(fw, fd)
    for name in ("Consortium",) + OPS:
        sel = np.ones(len(sx), bool) if name == "Consortium" else ops == name
        d3 = third_nearest(fx, fy, dz, sx[sel], sy[sel])
        x, c = weighted_cdf(d3, fw)
        ax.step(np.minimum(np.r_[0, x], xmax * 1.5), np.r_[0, c], where="post",
                **SCENARIO[name])
        rows.append((name, fw[d3 <= D3_STAR].sum() / fw.sum(), wd[d3 <= D3_STAR].sum() / wd.sum()))
    ax.axvline(D3_STAR, color="#444444", lw=0.7, ls=(0, (1, 1.5)), zorder=0)
    # label above the plot area, on the line: never on top of a curve
    ax.annotate(rf"$d^\star_3 \approx {D3_STAR:.0f}$ m", xy=(D3_STAR, 1.0), xycoords=("data", "axes fraction"),
                xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=7,
                annotation_clip=False)
    ax.set_xlim(0, xmax); ax.set_ylim(0, 1.0); ax.margins(0)
    ax.set_xlabel("distance from drone to its 3rd-nearest site (m)")
    ax.set_ylabel("fraction of flight time")
    ax.grid(True, lw=0.3, color="#dddddd"); ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    if legend_outside:   # legend beside the plot: it cannot cover a curve
        ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=7, frameon=False, handlelength=2.6)
    else:
        ax.legend(loc="lower right", bbox_to_anchor=(1.0, 0.05), fontsize=6.5, frameon=True, framealpha=0.92,
                  edgecolor="none", handlelength=2.4)
    return rows


def figure_pooled(fx, fy, fw, fd, dz, sx, sy, ops, roi, domain, demo):
    fig = plt.figure(figsize=(6.3, 2.45))
    gs = fig.add_gridspec(1, 4, width_ratios=[1.0, 0.035, 0.62, 1.0], wspace=0.0)
    axm, axc = fig.add_subplot(gs[0]), fig.add_subplot(gs[3])
    cax = axm.inset_axes([1.03, 0.0, 0.045, 1.0])   # colorbar exactly as tall as the map
    extent, clipped = map_extent(fx, fy, roi, domain, FRAME)
    hb = draw_map(axm, fx, fy, fw, fd, sx, sy, roi, domain, extent)
    axm.set_title("(a) Flight time and cell sites", fontsize=8.5, pad=15)
    colorbar(fig, hb, cax)
    axm.legend(handles=map_legend_handles(clipped), loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=3,
               fontsize=6.5, frameon=False, handlelength=1.4, columnspacing=0.8, handletextpad=0.4)
    rows = draw_cdf(axc, fx, fy, fw, fd, dz, sx, sy, ops, legend_outside=True)
    axc.set_box_aspect(1)                               # same height as the square map: titles line up
    axc.set_title("(b) Three sites within reach?", fontsize=8.5, pad=15)
    return fig, rows


def figure_per_operator(fx, fy, fw, fd, sx, sy, ops, roi, domain, demo, show_others=True):
    """Second figure: one map per operator, side by side. Its sites in black; the other operators'
    sites faint (show_others) so each panel reads as 'what this operator adds to the consortium'.
    Lets a reader count sites per operator: BM-39 (lead author's call, record it)."""
    fig = plt.figure(figsize=(6.3, 2.35))
    gs = fig.add_gridspec(1, 3, wspace=0.05)
    extent, clipped = map_extent(fx, fy, roi, domain, FRAME)
    axes = []
    for k, (op, tag) in enumerate(zip(OPS, "abc")):
        ax = fig.add_subplot(gs[k]); sel = ops == op; axes.append(ax)
        hb = draw_map(ax, fx, fy, fw, fd, sx[sel], sy[sel], roi, domain, extent,
                      others=(sx[~sel], sy[~sel]) if show_others else None, scale=(k == 0))
        ax.set_title(f"({tag}) Operator {op}", fontsize=8.5, pad=3)
    colorbar(fig, hb, axes[-1].inset_axes([1.04, 0.0, 0.045, 1.0]))
    handles = map_legend_handles(clipped)[:2]
    if show_others:
        handles += [Line2D([], [], marker="^", ls="none", ms=4.5, mfc="black", mec="black", mew=0.6,
                           label="this operator\u2019s site"),
                    Line2D([], [], marker="^", ls="none", ms=4.0, mfc="none", mec="#b5b5b5", mew=0.5,
                           label="other operators\u2019 sites")]
    else:
        handles += map_legend_handles(clipped)[2:]
    axes[1].legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.03), ncol=len(handles),
                   fontsize=7, frameon=False, handlelength=1.6, columnspacing=1.2, handletextpad=0.4)
    return fig, []


# ------------------------------------------------------------------------------------------ main
def demo_data():
    rng = np.random.default_rng(7)
    th = np.linspace(0, 2 * np.pi, 80)
    roi = (550 * np.cos(th) * 1.3, 420 * np.sin(th))
    domain = (np.array([-1600, 1600, 1600, -1600, -1600]), np.array([-1300, -1300, 1300, 1300, -1300]))
    parts, ops = [], []
    for op, n, spread, off in (("A", 30, 700, (-100, 0)), ("B", 23, 1000, (500, 300)), ("C", 56, 1700, (0, 0))):
        p = rng.normal(0, spread, (n, 2)) + off
        if op == "C":
            p = p[np.hypot(*p.T) > 800]
        parts.append(p); ops += [op] * len(p)
    sxy = np.vstack(parts); sx, sy, ops = sxy[:, 0], sxy[:, 1], np.array(ops)
    fx, fy, fw, fd = [], [], [], []
    for k in range(20):
        n = 1500 if k == 0 else 200
        p = rng.normal(0, 350, 2) + (np.array([300, 100]) if k == 0 else 0)
        steps = rng.normal(0, 25, (n, 2)).cumsum(0) * 0.6 + p
        fx += list(steps[:, 0]); fy += list(steps[:, 1]); fw += [1.0] * n; fd += [k] * n
    fx, fy, fw, fd = map(np.asarray, (fx, fy, fw, fd))
    dz = rng.uniform(30, 90, len(fx)) - H_RX_M
    return fx, fy, fw, fd, dz, sx, sy, ops, roi, domain


# Accepted column names, first match wins (case-insensitive). COLS above is tried first.
CANDIDATES = dict(
    drone=["uas_id", "uas", "serial_anon", "serial", "drone_id", "drone", "pseudonym"],
    session=["session_id", "session", "flight_id", "flight", "sess_id"],
    t=["t_utc", "t_s", "t", "time_s", "ts", "t_unix", "epoch_s", "timestamp", "time", "datetime", "dt"],
    lat=["lat", "latitude", "lat_deg", "drone_lat"],
    lon=["lon", "lng", "longitude", "lon_deg", "drone_lon"],
    in_domain=["in_domain", "in_dom", "domain"],
    agl=["agl_m", "agl", "alt_agl_m", "h_agl_m"],
    site_lat=["lat", "latitude", "site_lat"],
    site_lon=["lon", "lng", "longitude", "site_lon"],
    operator=["operator", "op", "scenario", "operadora", "carrier"],
)
REQUIRED = dict(samples=("drone", "session", "t", "lat", "lon"), sites=("site_lat", "site_lon", "operator"))
OPTIONAL = ("in_domain", "agl")


def resolve(df, keys, path, optional=()):
    """Map each logical key to a real column; on failure list the columns the file actually has."""
    low = {c.lower(): c for c in df.columns}
    out, missing = {}, []
    for k in keys + tuple(optional):
        for cand in [COLS[k]] + CANDIDATES[k]:
            if cand.lower() in low:
                out[k] = low[cand.lower()]
                break
        else:
            if k not in optional:
                missing.append(k)
    if missing:
        raise SystemExit(f"\n{path}: no column found for {missing}.\n"
                         f"Columns in the file: {list(df.columns)}\n"
                         f"Set the right names in COLS at the top of this script.")
    return out


def seconds(col):
    """Time column -> float seconds (datetimes via .dt.total_seconds(), rule T12)."""
    import pandas as pd
    if pd.api.types.is_datetime64_any_dtype(col):
        return (col - col.min()).dt.total_seconds()
    if pd.api.types.is_timedelta64_dtype(col):
        return col.dt.total_seconds()
    if pd.api.types.is_numeric_dtype(col):
        return col.astype(float)
    dt = pd.to_datetime(col, utc=True)                    # ISO strings such as 2025-11-08T14:03:12Z
    return (dt - dt.min()).dt.total_seconds()


def parse_op_map(text):
    """'op1=A,op2=B,op3=C' -> dict; keeps the op* -> A/B/C mapping in the command, not in the paper."""
    return dict(p.split("=", 1) for p in text.split(",")) if text else {}


def load(args):
    import pandas as pd
    from pyproj import Transformer
    smp = pd.read_parquet(args.samples)
    c = resolve(smp, REQUIRED["samples"], args.samples, OPTIONAL)
    if "in_domain" in c:
        smp = smp[smp[c["in_domain"]].astype(bool)]
    smp = smp.assign(_t_s=seconds(smp[c["t"]]))
    smp = smp.sort_values([c["session"], "_t_s"]).reset_index(drop=True)
    COLS.update(session=c["session"], t="_t_s")           # used by the fallback in time_weights
    print(f"samples: {len(smp)} rows, columns used: {c}")

    site = pd.read_parquet(args.sites)
    cs = resolve(site, REQUIRED["sites"], args.sites)
    ops = site[cs["operator"]].astype(str).map(lambda v: parse_op_map(args.op_map).get(v, v)).to_numpy()
    unknown = sorted(set(ops) - set(OPS))
    if unknown:
        raise SystemExit(f"\n{args.sites}: operator values {unknown} are not {list(OPS)}.\n"
                         f"Pass the mapping, e.g. --op-map {','.join(f'{u}=?' for u in unknown)}")
    print(f"sites: {len(site)} rows, columns used: {cs}")

    g = json.load(open(args.roi)); geom = g["features"][0]["geometry"] if "features" in g else g
    lon0, lat0 = np.array(geom["coordinates"][0] if geom["type"] == "Polygon" else geom["coordinates"][0][0]).mean(0)
    origin = Transformer.from_crs(4326, EPSG_LOCAL, always_xy=True).transform(lon0, lat0)
    fw = time_weights(smp)
    fx, fy = to_local(smp[c["lat"]], smp[c["lon"]], origin)
    fd = smp[c["drone"]].to_numpy()
    if "agl" in c:
        dz = smp[c["agl"]].to_numpy(float) - H_RX_M
    else:
        print("warning: no AGL column; using horizontal distance only (dz = 0)")
        dz = np.zeros(len(smp))
    sx, sy = to_local(site[cs["site_lat"]], site[cs["site_lon"]], origin)
    return fx, fy, fw, fd, dz, sx, sy, ops, ring_xy(args.roi, origin), ring_xy(args.domain, origin)


def main():
    ap = argparse.ArgumentParser()
    for a in ("samples", "sites", "roi", "domain"):
        ap.add_argument(f"--{a}")
    ap.add_argument("--out", default=".")
    ap.add_argument("--only", choices=("both", "consortium", "operators"), default="both",
                    help="which figure(s) to write; default both")
    ap.add_argument("--frame", choices=("domain", "flights"), default="domain",
                    help="domain: whole analysis domain in frame (default); flights: zoom on the flights")
    ap.add_argument("--no-others", action="store_true",
                    help="operator figure: hide the other operators' sites (faint grey by default)")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--op-map", default="", help="operator labels in sites.parquet -> A/B/C, e.g. op1=A,op2=B,op3=C")
    args = ap.parse_args()
    global FRAME
    FRAME = args.frame

    fx, fy, fw, fd, dz, sx, sy, ops, roi, domain = demo_data() if args.demo else load(args)
    import os
    os.makedirs(args.out, exist_ok=True)                 # create paper/figures if it does not exist
    tag = "_demo" if args.demo else ""
    jobs = []
    if args.only in ("both", "consortium"):            # Fig. X: consortium map + d_(3) CDF
        jobs.append(("fig_scenario", figure_pooled(fx, fy, fw, fd, dz, sx, sy, ops, roi, domain, args.demo)))
    if args.only in ("both", "operators"):             # Fig. Y: the three operators side by side
        jobs.append(("fig_scenario_operators",
                     figure_per_operator(fx, fy, fw, fd, sx, sy, ops, roi, domain, args.demo,
                                         show_others=not args.no_others)))
    for name, (fig, rows) in jobs:
        if args.demo:
            fig.text(0.99, -0.07, "synthetic demo data", ha="right", va="top", fontsize=6, color="#b00")
        stem = f"{args.out}/{name}{tag}"
        for ext in ("pdf", "png"):
            fig.savefig(f"{stem}.{ext}", dpi=300)
        print(f"wrote {stem}.pdf")
        if rows:
            with open(f"{stem}_numbers.csv", "w") as f:
                f.write(f"scenario,frac_time_d3_le_{D3_STAR:.0f}m_pooled,frac_time_d3_le_{D3_STAR:.0f}m_drone_weighted\n")
                for r in rows:
                    f.write(f"{r[0]},{r[1]:.3f},{r[2]:.3f}\n")
            print(open(f"{stem}_numbers.csv").read())

if __name__ == "__main__":
    main()