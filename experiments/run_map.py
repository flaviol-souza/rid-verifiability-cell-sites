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
    # a cell is 'inventory edge' if any part of it is within R of the site bounding box edge (possibly truncated)
    cells["inventory_edge"] = geo.bbox_edge_distance_m(ax_, ay_, cells["cell_x_m"], cells["cell_y_m"]) \
        < R + a.cell_m / np.sqrt(2)
    out = root / a.out
    out.mkdir(parents=True, exist_ok=True)
    cells.to_csv(out / "cells.csv", index=False, lineterminator="\n")

    fig, ax = plt.subplots(figsize=(4.4, 4.6))
    show = cells[cells["time_s"] >= a.min_time_s]
    cmap = LinearSegmentedColormap.from_list("blue", BLUE_RAMP)
    sc = ax.scatter(show["cell_x_m"], show["cell_y_m"], c=show[f"frac_V3_D{int(D)}"], cmap=cmap, vmin=0, vmax=1,
                    marker="s", s=(a.cell_m / 40) ** 2 * 4, linewidths=0)
    edge = show[show["inventory_edge"]]
    if len(edge):
        ax.scatter(edge["cell_x_m"], edge["cell_y_m"], marker="s", s=(a.cell_m / 40) ** 2 * 4, facecolors="none",
                   edgecolors="#eb6834", linewidths=0.8, label=f"within R of inventory edge (possibly truncated)")
    sx, sy = local_xy_m(sites["lat"], sites["lon"], lat0, lon0)
    ax.scatter(sx, sy, marker="^", s=12, color="#1f1f1e", label="cell site", zorder=3)
    roi_path = root / cfg["stage_a"]["paths"]["roi"]
    if roi_path.exists():
        gj = json.loads(roi_path.read_text())
        geom = gj["features"][0]["geometry"] if "features" in gj else gj
        rings = geom["coordinates"] if geom["type"] == "Polygon" else [p[0] for p in geom["coordinates"]]
        for ring in rings[:1] if geom["type"] == "Polygon" else rings:
            rx, ry = local_xy_m([c[1] for c in ring], [c[0] for c in ring], lat0, lon0)
            ax.plot(rx, ry, color="#5f5e58", linewidth=0.9, linestyle="--", label="event zone (RoI)")
    cb = fig.colorbar(sc, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label(f"fraction of time verifiable (V3, D = {int(D)} m)", fontsize=8)
    cb.ax.tick_params(labelsize=7)
    ax.set_aspect("equal")
    ax.set_xlabel("x (m)", fontsize=8); ax.set_ylabel("y (m)", fontsize=8)
    ax.set_title(f"{a.scenario}, R = {int(R)} m", fontsize=9)
    ax.tick_params(labelsize=7)
    h, l = ax.get_legend_handles_labels()
    fig.legend(h, l, fontsize=7, frameon=False, loc="lower center", ncol=1)   # below the axes, never over the data
    fig.tight_layout(rect=(0, 0.04 + 0.04 * len(l), 1, 1))
    fig.savefig(out / f"fig_map_V3_{a.scenario}.pdf", metadata={"CreationDate": None, "ModDate": None})
    fig.savefig(out / f"fig_map_V3_{a.scenario}.png", dpi=200)
    print(f"{len(cells)} cells ({len(show)} drawn) -> {out.relative_to(root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
