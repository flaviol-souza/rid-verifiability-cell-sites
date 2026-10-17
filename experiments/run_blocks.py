"""Blocks O/V (and S via overrides): scenarios × sweep levels × seeds → per-session metrics (long table).

Idempotent: each (scenario, level, seed) cell is written to its own parquet; existing cells are skipped.
Usage (WSL, clean tree):
    python experiments/run_blocks.py --config experiments/configs/reference.yaml --out results/stage_b/blockO [--seeds 0-19]
Writes only aggregates per session (no positions). Observations are not stored (re-generable from seed).
"""
import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # repo root, for analysis/
from analysis import observability as ob
from analysis import verifiability as vf
from drs.channel import observe, pathloss


def _git_commit(root):
    try:
        rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root,
                               capture_output=True, text=True, check=True).stdout.strip()
        return rev + ("-dirty" if dirty else "")
    except Exception:
        return "unknown"


def scenario_sites(sites: pd.DataFrame, scenario: str) -> pd.DataFrame:
    if scenario == "consortium":
        return sites
    return sites[sites["operator"].str.split("|").apply(lambda ops: scenario in ops)]


def apply_variant(samples: pd.DataFrame, sample_filter: str, agl: str) -> pd.DataFrame:
    s = samples
    if sample_filter == "exclude_group1":
        s = s[s["group_size"] > 1]
    elif sample_filter == "exclude_unanchored":
        s = s[s["agl_anchor"] != "none"]
    if agl == "dem":
        s = s.assign(agl_m=s["agl_dem_m"])
    return s.reset_index(drop=True)


def levels(b: dict, ch: dict) -> list[tuple[float, float]]:
    """(range_m, gamma_dbm) pairs for the configured sweep."""
    if b.get("sweep", "range") == "range":
        return [(float(R), pathloss.gamma_for_range_dbm(R, ch)) for R in b["range_grid_m"]]
    return [(pathloss.implied_range_m(dict(ch, sniffer_sens_dbm=g)), float(g)) for g in b["gamma_sweep_dbm"]]


def cell_metrics(samples, sites, ch, seed, b, gap_cap_s) -> pd.DataFrame:
    obs = observe.observe(samples, sites, ch, seed)
    s = samples.sort_values(["session_id", "t_utc"], kind="mergesort").reset_index(drop=True)
    w = ob.time_weights_s(s, gap_cap_s)
    n = ob.n_observers(s, obs).to_numpy()
    pb = vf.per_sample_bounds_fast(obs, ch["eta"], ch["shadow_sigma_db"]).set_index("sample_id")
    s3 = s["sample_id"].map(pb["sigma_h_v3_m"]).fillna(np.inf).to_numpy()
    s4 = s["sample_id"].map(pb["sigma_h_v4_m"]).fillna(np.inf).to_numpy()
    flags = {f"observable_k{k}": n >= k for k in b["k_levels"]}
    for D in b["verif_scale_m"]:
        flags[f"V3_D{int(D)}"] = (n >= 3) & (s3 <= D)
        flags[f"V4_D{int(D)}"] = (n >= 4) & (s4 <= D)
    den = w.groupby(s["session_id"]).sum()
    serial = s.groupby("session_id")["uas_id"].first()
    rows = []
    for name, f in flags.items():
        frac = (pd.Series(f.astype(float)) * w).groupby(s["session_id"]).sum() / den
        rows.append(pd.DataFrame({"session_id": frac.index, "uas_id": serial.loc[frac.index].to_numpy(),
                                  "metric": name, "value": frac.to_numpy()}))
    return pd.concat(rows, ignore_index=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="experiments/configs/reference.yaml")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seeds", default=None, help="e.g. 0-4 (default: config seeds)")
    ap.add_argument("--scenarios", default=None, help="comma list (default: consortium + every operator)")
    ap.add_argument("--override", action="append", default=[], help="channel override key=value (block S)")
    ap.add_argument("--sample-filter", default="none", choices=["none", "exclude_group1", "exclude_unanchored"],
                    help="block S: drop samples from single-row messages, or sessions without an AGL anchor")
    ap.add_argument("--agl", default="anchored", choices=["anchored", "dem"], help="block S: AGL variant used as drone height")
    a = ap.parse_args()
    root = Path(a.root).resolve()
    cfg = yaml.safe_load((root / a.config).read_text())
    b = cfg["stage_b"]
    ch = yaml.safe_load((root / b["channel"]).read_text())
    for ov in a.override:
        k, v = ov.split("=", 1)
        ch[k] = type(ch[k])(v) if k in ch else float(v)
    interim = root / cfg["stage_a"]["paths"]["interim_dir"]
    samples = apply_variant(pd.read_parquet(interim / "samples.parquet"), a.sample_filter, a.agl)
    sites = pd.read_parquet(interim / "sites.parquet")
    ops = sorted({o for ops in sites["operator"].str.split("|") for o in ops})
    scenarios = a.scenarios.split(",") if a.scenarios else ["consortium"] + ops
    seeds = (list(range(int(a.seeds.split("-")[0]), int(a.seeds.split("-")[1]) + 1)) if a.seeds else b["seeds"])
    out = root / a.out
    (out / "cells").mkdir(parents=True, exist_ok=True)
    manifest = []
    for R, gamma in levels(b, ch):
        chg = dict(ch, sniffer_sens_dbm=gamma)
        trunc = pathloss.tail_heard_prob(chg["r_max_m"], chg) > chg["tail_max"]
        for sc in scenarios:
            for seed in seeds:
                f = out / "cells" / f"{ch['family']}__{sc}__R{int(round(R))}__s{seed:02d}.parquet"
                manifest.append({"family": ch["family"], "scenario": sc, "range_m": round(R, 1), "gamma_dbm": round(gamma, 3),
                                 "seed": seed, "truncated": bool(trunc), "file": f.name})
                if f.exists():
                    continue
                m = cell_metrics(samples, scenario_sites(sites, sc), chg, seed, b, cfg["stage_a"]["session_gap_s"])
                m.insert(0, "seed", seed); m.insert(0, "range_m", round(R, 1)); m.insert(0, "scenario", sc)
                m.insert(0, "family", ch["family"])
                m.to_parquet(f, index=False)
    man = pd.DataFrame(manifest)
    man.to_csv(out / "manifest.csv", index=False, lineterminator="\n")
    tbl = pd.concat([pd.read_parquet(out / "cells" / r) for r in man["file"]], ignore_index=True)
    tbl.to_parquet(out / "session_metrics.parquet", index=False)
    prov = {"created_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"), "git_commit": _git_commit(root),
            "channel": ch, "stage_b": b, "scenarios": scenarios, "seeds": seeds, "overrides": a.override,
            "sample_filter": a.sample_filter, "agl": a.agl, "n_samples": int(len(samples)),
            "n_cells": int(len(man)), "n_truncated_cells": int(man["truncated"].sum())}
    (out / "provenance.yaml").write_text(yaml.safe_dump(prov, sort_keys=True), newline="\n")
    print(f"{len(man)} cells ({int(man['truncated'].sum())} truncated) -> {out.relative_to(root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
