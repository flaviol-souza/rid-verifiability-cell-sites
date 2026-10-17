"""Stage B pilot: observations for one scenario, one γ and one seed, plus observability/verifiability summary.

PILOT ONLY (measures cost and checks the pipeline). Results do not enter the paper before G2 (channel anchoring).
Usage (WSL, clean tree):
    python experiments/run_stage_b.py --config experiments/configs/reference.yaml [--gamma -95] [--seed 0] [--scenario consortium]
"""
import argparse
import datetime as dt
import hashlib
import subprocess
import sys
import time
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


def run_pilot(cfg: dict, root: Path, scenario: str, gamma: float | None, seed: int) -> dict:
    b = cfg["stage_b"]
    ch = yaml.safe_load((root / b["channel"]).read_text())
    if gamma is not None:
        ch["sniffer_sens_dbm"] = float(gamma)
    interim = root / cfg["stage_a"]["paths"]["interim_dir"]
    samples = pd.read_parquet(interim / "samples.parquet")
    sites = pd.read_parquet(interim / "sites.parquet")
    if scenario != "consortium":
        sites = sites[sites["operator"].str.split("|").apply(lambda ops: scenario in ops)]
    t0 = time.time()
    obs = observe.observe(samples, sites, ch, seed)
    t_obs = time.time() - t0
    samples = samples.sort_values(["session_id", "t_utc"], kind="mergesort").reset_index(drop=True)
    w = ob.time_weights_s(samples, cfg["stage_a"]["session_gap_s"])
    n = ob.n_observers(samples, obs)
    pb = vf.per_sample_bounds(obs, ch["eta"], ch["shadow_sigma_db"]).set_index("sample_id")
    s3 = samples["sample_id"].map(pb["sigma_h_v3_m"]).fillna(np.inf).to_numpy()
    s4 = samples["sample_id"].map(pb["sigma_h_v4_m"]).fillna(np.inf).to_numpy()

    def frac(flag):
        per = (pd.Series(flag.astype(float)) * w).groupby(samples["session_id"]).sum() / w.groupby(samples["session_id"]).sum()
        return round(float(per.mean()), 4)

    out = {"scenario": scenario, "n_sites": int(len(sites)), "seed": seed, "gamma_dbm": ch["sniffer_sens_dbm"],
           "implied_range_m": round(pathloss.implied_range_m(ch), 1),
           "tail_heard_prob_at_rmax": round(pathloss.tail_heard_prob(ch["r_max_m"], ch), 4),
           "truncated": pathloss.tail_heard_prob(ch["r_max_m"], ch) > ch["tail_max"],
           "max_untruncated_range_m": round(pathloss.max_untruncated_range_m(ch), 1),
           "n_samples": int(len(samples)), "n_pairs": int(len(obs)), "observe_seconds": round(t_obs, 2)}
    for k in b["k_levels"]:
        out[f"observable_k{k}"] = frac(n.to_numpy() >= k)
    for D in b["verif_scale_m"]:
        out[f"V3_D{int(D)}"] = frac((n.to_numpy() >= 3) & (s3 <= D))
        out[f"V4_D{int(D)}"] = frac((n.to_numpy() >= 4) & (s4 <= D))
    return out, obs, ch


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="experiments/configs/reference.yaml")
    ap.add_argument("--root", default=".")
    ap.add_argument("--scenario", default=None)
    ap.add_argument("--gamma", type=float, default=None)
    ap.add_argument("--range", dest="range_m", type=float, default=None, help="target implied range R (m); overrides --gamma")
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()
    root = Path(a.root).resolve()
    cfg = yaml.safe_load((root / a.config).read_text())
    scenario = a.scenario or cfg["stage_b"]["scenario"]
    seed = cfg["stage_b"]["seeds"][0] if a.seed is None else a.seed
    gamma = a.gamma
    if a.range_m is not None:
        ch0 = yaml.safe_load((root / cfg["stage_b"]["channel"]).read_text())
        gamma = pathloss.gamma_for_range_dbm(a.range_m, ch0)
    summary, obs, ch = run_pilot(cfg, root, scenario, gamma, seed)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = root / cfg["stage_b"]["paths"]["results_dir"] / "pilot" / stamp
    out.mkdir(parents=True)
    raw = root / cfg["stage_b"]["paths"]["observations_dir"] / scenario / f"R{int(round(summary['implied_range_m']))}"
    raw.mkdir(parents=True, exist_ok=True)
    obs_path = raw / f"seed_{seed:02d}.parquet"
    obs.to_parquet(obs_path, index=False)
    prov = {"created_utc": stamp, "git_commit": _git_commit(root), "channel": ch, "summary": summary,
            "observations_sha256": hashlib.sha256(obs_path.read_bytes()).hexdigest(),
            "note": "PILOT — not for the paper before G2"}
    (out / "provenance.yaml").write_text(yaml.safe_dump(prov, sort_keys=True), newline="\n")
    pd.DataFrame([summary]).T.rename(columns={0: "value"}).to_csv(out / "summary.csv", lineterminator="\n")
    print(pd.DataFrame([summary]).T.rename(columns={0: "value"}).to_string())
    if summary["truncated"]:
        print("\nWARNING: P(heard at r_max) > tail_max — observability here is a LOWER bound (inventory truncation).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
