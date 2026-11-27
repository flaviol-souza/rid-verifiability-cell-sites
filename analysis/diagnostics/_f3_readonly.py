"""Read-only F3 diagnostic; generated tables are not pipeline inputs."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parents[2]))
import numpy as np
import pandas as pd
import yaml
from analysis import geometry as geo
from analysis import observability as ob
from drs.channel import observe, pathloss

ROOT = Path(__file__).parents[2]
OUT = ROOT / "results/stage_b/mechanism/diagnostics"
OUT.mkdir(parents=True, exist_ok=True)
cfg = yaml.safe_load((ROOT / "experiments/configs/reference.yaml").read_text())
b = cfg["stage_b"]
ch = yaml.safe_load((ROOT / b["channel"]).read_text())
samples = pd.read_parquet(ROOT / cfg["stage_a"]["paths"]["interim_dir"] / "samples.parquet").sort_values(["session_id", "t_utc"], kind="mergesort").reset_index(drop=True)
all_sites = pd.read_parquet(ROOT / cfg["stage_a"]["paths"]["interim_dir"] / "sites.parquet")
cut = geo.load_cut_ring(ROOT / cfg["stage_a"]["paths"]["anatel_cut"])
lat0, lon0 = geo.common_origin(all_sites)
x, y = geo.local_xy_m(samples["lat"], samples["lon"], lat0, lon0)
edge = geo.inventory_edge_distance_m(all_sites, x, y, lat0, lon0, cut)[0]
w = ob.time_weights_s(samples, cfg["stage_a"]["session_gap_s"])
R, D = 1000.0, float(b["verif_scale_ref_m"])
ch_r = dict(ch, sniffer_sens_dbm=pathloss.gamma_for_range_dbm(R, ch))

def weighted_quantile(values, weights, q):
    values, weights = np.asarray(values, dtype=float), np.asarray(weights, dtype=float)
    order = np.argsort(values, kind="mergesort")
    cumulative = np.cumsum(weights[order])
    return float(values[order][np.searchsorted(cumulative, q * cumulative[-1], side="left")])

summary_rows = []
for scenario in ["consortium", "VIVO", "CLARO", "TIM"]:
    sites = all_sites if scenario == "consortium" else all_sites[all_sites["operator"].str.split("|").apply(lambda v: scenario in v)]
    d3 = geo.session_geometry(samples, sites, all_sites, w, 3, float(b["range_ref_m"]), cut)[["session_id", "d3_median_m"]]
    seed_frames = []
    for seed in b["seeds"]:
        observations = observe.observe(samples, sites, ch_r, int(seed))
        bounds = geo.inventory_bounded_sample_v3(samples, sites, observations, ch["r_max_m"], ch["sniffer_height_m"], ch["eta"], ch["shadow_sigma_db"], D, edge)
        n_in = observations.loc[observations["heard"]].groupby("sample_id").size()
        bounds["n_in"] = bounds["sample_id"].map(n_in).fillna(0).astype(int)
        bounds["session_id"] = bounds["sample_id"].map(samples.set_index("sample_id")["session_id"])
        bounds["uas_id"] = bounds["sample_id"].map(samples.set_index("sample_id")["uas_id"])
        bounds["weight_s"] = bounds["sample_id"].map(pd.Series(w.to_numpy(), index=samples["sample_id"]))
        bounds["seed"] = seed
        seed_frames.append(bounds)
    sb = pd.concat(seed_frames, ignore_index=True).merge(d3, on="session_id", how="left")
    sessions=[]
    for (sid, uid), g in sb.groupby(["session_id", "uas_id"], sort=True):
        den=g.weight_s.sum()
        sessions.append({"scenario":scenario,"session_id":sid,"uas_id":uid,"d3_median_m":g.d3_median_m.iloc[0],
          "v3_lower":(g.v3_lower*g.weight_s).sum()/den,"v3_upper":(g.v3_upper*g.weight_s).sum()/den,
          "n_star_p10_weighted":weighted_quantile(g.n_star,g.weight_s,.1)})
    sessions=pd.DataFrame(sessions)
    distant=sessions[sessions.d3_median_m>200]
    low=distant[distant.v3_upper<.1]
    high=set(sessions.loc[(sessions.v3_upper-sessions.v3_lower)>.5,"session_id"])
    high_samples=sb[sb.session_id.isin(high)].copy()
    gain=(high_samples.v3_lower==0)&(high_samples.v3_upper==1)
    high_samples["gain_reason"]=np.where(~gain,"not_newly_verifiable",np.where(high_samples.n_in<3,"receiver_count_completion","information_addition"))
    denominator=high_samples.weight_s.sum()
    shares=high_samples.groupby("gain_reason").weight_s.sum()/denominator if denominator else pd.Series(dtype=float)
    summary_rows.append({"scenario":scenario,"n_sessions":len(sessions),"n_distant":len(distant),"fraction_distant_upper_below_0_1":len(low)/len(distant) if len(distant) else np.nan,"max_distant_v3_upper":distant.v3_upper.max() if len(distant) else np.nan,"min_flight_n_star_p10_weighted":low.n_star_p10_weighted.min() if len(low) else np.nan,"n_high_interval":len(high),"high_interval_time_receiver_count_completion":shares.get("receiver_count_completion",0.),"high_interval_time_information_addition":shares.get("information_addition",0.),"high_interval_time_not_newly_verifiable":shares.get("not_newly_verifiable",0.)})
    sessions.to_csv(OUT/f"f3_sessions_{scenario}.csv",index=False,lineterminator="\n")
pd.DataFrame(summary_rows).to_csv(OUT/"f3_diagnostic_summary.csv",index=False,lineterminator="\n")
print(pd.DataFrame(summary_rows).to_string(index=False))
