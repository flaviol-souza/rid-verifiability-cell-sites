"""Map of verifiability (V3 at the reference D) for one scenario and the reference range, averaged over seeds.

Usage: python experiments/run_map.py --config experiments/configs/reference.yaml --out results/stage_b/map [--seeds 0-4]
"""
import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis import geometry as geo  # noqa: E402
from analysis import observability as ob  # noqa: E402
from analysis import spatial  # noqa: E402
from analysis import verifiability as vf  # noqa: E402
from drs.channel import observe, pathloss  # noqa: E402
from drs.geo import local_xy_m  # noqa: E402

BLUE_RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#1c5cab", "#104281", "#0d366b"]   # one hue, light→dark


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="experiments/configs/reference.yaml")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seeds", default="0-4")
    ap.add_argument("--scenario", default="consortium")
    ap.add_argument("--cell-m", type=float, default=100.0)
    ap.add_argument("--min-time-s", type=float, default=30.0, help="cells with less flight time are not drawn")
    ap.add_argument("--margin-m", type=float, default=300.0, help="view = flight cells ± margin (same for every scenario)")
    ap.add_argument("--full-extent", action="store_true", help="show the whole site inventory instead of the flight area")
    a = ap.parse_args()
    root = Path(a.root).resolve()
    cfg = yaml.safe_load((root / a.config).read_text())
    b = cfg["stage_b"]
    if b.get("range_ref_m") is None:
        print("ERROR: stage_b.range_ref_m is not set", file=sys.stderr)
        return 2
    ch = yaml.safe_load((root / b["channel"]).read_text())
    ch["sniffer_sens_dbm"] = pathloss.gamma_for_range_dbm(float(b["range_ref_m"]), ch)
    interim = root / cfg["stage_a"]["paths"]["interim_dir"]
    samples = pd.read_parquet(interim / "samples.parquet").sort_values(["session_id", "t_utc"], kind="mergesort").reset_index(drop=True)
    all_sites = pd.read_parquet(interim / "sites.parquet")
    sites = all_sites
    if a.scenario != "consortium":
        sites = all_sites[all_sites["operator"].str.split("|").apply(lambda ops: a.scenario in ops)]
    lat0, lon0 = geo.common_origin(all_sites)          # same frame for every scenario → maps comparable cell by cell
    R = float(b["range_ref_m"])
    w = ob.time_weights_s(samples, cfg["stage_a"]["session_gap_s"])
    D = float(b["verif_scale_ref_m"])
    lo, hi = (int(v) for v in a.seeds.split("-"))
    acc_obs, acc_v3 = np.zeros(len(samples)), np.zeros(len(samples))
    seeds = list(range(lo, hi + 1))
    for seed in seeds:
        obs = observe.observe(samples, sites, ch, seed)
        n = ob.n_observers(samples, obs).to_numpy()
        pb = vf.per_sample_bounds_fast(obs, ch["eta"], ch["shadow_sigma_db"]).set_index("sample_id")
        s3 = samples["sample_id"].map(pb["sigma_h_v3_m"]).fillna(np.inf).to_numpy()
        acc_obs += (n >= 1)
        acc_v3 += (n >= 3) & (s3 <= D)
    flags = {"observable_k1": acc_obs / len(seeds), f"V3_D{int(D)}": acc_v3 / len(seeds)}
    cells = spatial.grid_cells(samples, flags, w, lat0, lon0, a.cell_m)
    ax_, ay_ = local_xy_m(all_sites["lat"], all_sites["lon"], lat0, lon0)
    # inventory edge: the documented cut polygon if configured (exact), otherwise the site convex hull (conservative)
    cut_ring = geo.load_cut_ring(root / cfg["stage_a"]["paths"]["anatel_cut"]) \
        if cfg["stage_a"]["paths"].get("anatel_cut") else None
    cells["hull_margin_m"] = geo.hull_edge_distance_m(ax_, ay_, cells["cell_x_m"], cells["cell_y_m"]) - a.cell_m / np.sqrt(2)
    cm, basis = geo.inventory_edge_distance_m(all_sites, cells["cell_x_m"], cells["cell_y_m"], lat0, lon0, cut_ring)
    cells["inventory_margin_m"] = cm - a.cell_m / np.sqrt(2)
    cells["inventory_edge"] = cells["inventory_margin_m"] < R
    sxs, sys_ = local_xy_m(samples["lat"], samples["lon"], lat0, lon0)
    hull_m = geo.hull_edge_distance_m(ax_, ay_, sxs, sys_)
    inv_m, _ = geo.inventory_edge_distance_m(all_sites, sxs, sys_, lat0, lon0, cut_ring)
    m_min = float(inv_m.min())
    report = {"basis": basis, "range_m": R,
              "min_sample_distance_to_inventory_edge_m": round(m_min, 1),
              "p05_sample_distance_to_inventory_edge_m": round(float(np.percentile(inv_m, 5)), 1),
              "time_share_within_R_of_inventory_edge": round(float(w[inv_m < R].sum() / w.sum()), 4),
              "min_sample_distance_to_site_hull_m": round(float(hull_m.min()), 1),
              "configured_r_max_m": ch["r_max_m"],
              "max_untruncated_range_at_configured_r_max_m": round(pathloss.max_untruncated_range_m(ch), 1),
              "max_r_max_supported_by_inventory_m": round(m_min, 1),
              "max_untruncated_range_if_r_max_raised_m": round(pathloss.max_untruncated_range_m({**ch, "r_max_m": m_min}), 1)}
    (root / a.out).mkdir(parents=True, exist_ok=True)
    (root / a.out / "inventory_margin.json").write_text(json.dumps(report, indent=2) + "\n")
    out = root / a.out
    out.mkdir(parents=True, exist_ok=True)
    cells.to_csv(out / "cells.csv", index=False, lineterminator="\n")

    fig, ax = plt.subplots(figsize=(4.4, 4.4))
    show = cells[cells["time_s"] >= a.min_time_s]
    cmap = LinearSegmentedColormap.from_list("blue", BLUE_RAMP)
    sc = ax.scatter(show["cell_x_m"], show["cell_y_m"], c=show[f"frac_V3_D{int(D)}"], cmap=cmap, vmin=0, vmax=1,
                    marker="s", s=(a.cell_m / 40) ** 2 * 4, linewidths=0)
    edge = show[show["inventory_edge"]]
    if len(edge):
        ax.scatter(edge["cell_x_m"], edge["cell_y_m"], marker="s", s=(a.cell_m / 40) ** 2 * 4, facecolors="none",
                   edgecolors="#eb6834", linewidths=0.8, label="within R of inventory edge (possibly truncated)")
    sx, sy = local_xy_m(sites["lat"], sites["lon"], lat0, lon0)
    if a.full_extent:
        n_out, lab = 0, "cell site"
    else:
        # view from ALL cells (not only drawn ones): identical for every scenario since the drone tracks are the same
        x0, x1 = cells["cell_x_m"].min() - a.cell_m / 2 - a.margin_m, cells["cell_x_m"].max() + a.cell_m / 2 + a.margin_m
        y0, y1 = cells["cell_y_m"].min() - a.cell_m / 2 - a.margin_m, cells["cell_y_m"].max() + a.cell_m / 2 + a.margin_m
        ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
        n_out = int((~((sx >= x0) & (sx <= x1) & (sy >= y0) & (sy <= y1))).sum())
        lab = f"cell site ({n_out} outside view)" if n_out else "cell site"
    ax.scatter(sx, sy, marker="^", s=12, color="#1f1f1e", label=lab, zorder=3, clip_on=True)
    roi_path = root / cfg["stage_a"]["paths"]["roi"]
    if roi_path.exists():
        gj = json.loads(roi_path.read_text())
        geom = gj["features"][0]["geometry"] if "features" in gj else gj
        rings = geom["coordinates"] if geom["type"] == "Polygon" else [p[0] for p in geom["coordinates"]]
        for ring in rings[:1] if geom["type"] == "Polygon" else rings:
            rx, ry = local_xy_m([c[1] for c in ring], [c[0] for c in ring], lat0, lon0)
            ax.plot(rx, ry, color="#5f5e58", linewidth=0.9, linestyle="--", label="event zone (RoI)", scalex=False, scaley=False)
    cb = fig.colorbar(sc, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label(f"fraction of time verifiable (V3, D = {int(D)} m)", fontsize=8)
    cb.ax.tick_params(labelsize=7)
    ax.set_aspect("equal")
    ax.set_xlabel("x (m)", fontsize=8); ax.set_ylabel("y (m)", fontsize=8)
    ax.set_title(f"{a.scenario}, R = {int(R)} m", fontsize=9)
    ax.tick_params(labelsize=7)
    h, l = ax.get_legend_handles_labels()
    fig.legend(h, l, fontsize=7, frameon=False, loc="lower center", ncol=1)   # below the axes, never over the data
    fig.tight_layout(rect=(0, 0.02 + 0.035 * len(l), 1, 1))
    fig.savefig(out / f"fig_map_V3_{a.scenario}.pdf", metadata={"CreationDate": None, "ModDate": None})
    fig.savefig(out / f"fig_map_V3_{a.scenario}.png", dpi=200)
    print(f"{len(cells)} cells ({len(show)} drawn) -> {out.relative_to(root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
