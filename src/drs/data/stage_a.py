"""Stage A orchestration and G0 evaluation."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from shapely.geometry import shape

from drs.data import agl, anonymize, clean, sites
from drs.geo import haversine_m


def _geom(path):
    gj = json.loads(Path(path).read_text())
    return shape(gj["features"][0]["geometry"] if "features" in gj else gj)


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_config(path="experiments/configs/reference.yaml") -> dict:
    return yaml.safe_load(Path(path).read_text())


class InputHashMismatch(RuntimeError):
    pass


def run(cfg: dict, root: Path = Path(".")) -> dict:
    a, p = cfg["stage_a"], {k: root / v for k, v in cfg["stage_a"]["paths"].items()}
    key = anonymize.load_key(a["hmac_key_env"])                       # fails before any output
    if a.get("anatel_sha256") and sha256(p["anatel"]) != a["anatel_sha256"]:
        raise InputHashMismatch(f"ANATEL extract hash {sha256(p['anatel'])} != config {a['anatel_sha256']}")
    raw = pd.read_csv(p["flights_raw"], dtype={"flight_id": str})
    flights = anonymize.anonymize_flights(raw, key, a["pseudonym_prefix"], a["pseudonym_hex_chars"])
    p["flights_anon"].parent.mkdir(parents=True, exist_ok=True)
    flights.to_csv(p["flights_anon"], index=False, lineterminator="\n")
    p["flights_anon"].with_suffix(".sha256").write_text(f"{sha256(p['flights_anon'])}  {p['flights_anon'].name}\n")

    df = flights.rename(columns={"timestamp": "t_utc"})
    df["t_utc"] = pd.to_datetime(df["t_utc"], utc=True)
    domain, roi = _geom(p["domain"]), _geom(p["roi"])
    log = clean.CleaningLog()
    steps = [("C1", clean.c1_exact_duplicates), ("C2", clean.c2_one_per_timestamp),
             ("C3", lambda d: clean.c3_outside_extent(d, domain)), ("C4", clean.c4_placeholders),
             ("C5", lambda d: clean.c5_sentinel_altitude(d, a["sentinel_min_alt_msl_m"])),
             ("C6", lambda d: clean.c6_sessionize(d, a["session_gap_s"])),
             ("C7", lambda d: agl.add_agl(d, str(p["dem"]))),
             ("C8", lambda d: clean.c8_domain_and_roi(d, domain, roi, a["min_agl_m"])),
             ("C9", lambda d: clean.c9_speed(d, a["max_ground_speed_mps"]))]
    agl_before_c8 = None
    for name, fn in steps:
        new = fn(df)
        if name == "C7":
            agl_before_c8 = new["agl_m"].copy()
        log.record(name, df, new)
        df = new

    df = df.sort_values(["session_id", "t_utc"], kind="mergesort").reset_index(drop=True)
    df.insert(0, "sample_id", np.arange(len(df)))
    samples = df[["sample_id", "session_id", "uas_id", "t_utc", "lat", "lon", "agl_m", "in_roi"]]
    site_tab = sites.collapse_sites(pd.read_csv(p["anatel"], sep=";", dtype=str))

    out = p["interim_dir"]; out.mkdir(parents=True, exist_ok=True)
    samples.to_parquet(out / "samples.parquet", index=False)
    site_tab.to_parquet(out / "sites.parquet", index=False)
    log.to_frame().to_csv(out / "cleaning_log.csv", index=False, lineterminator="\n")
    return {"samples": samples, "sites": site_tab, "log": log.to_frame(), "agl_before_c8": agl_before_c8,
            "domain": domain}


def g0_evaluate(samples: pd.DataFrame, log: pd.DataFrame, cfg: dict, domain) -> dict:
    """G0 (research.md). Criteria come only from cfg['g0']; never edit them after seeing data."""
    from shapely import contains_xy
    g = cfg["g0"]
    agl_q = np.percentile(samples["agl_m"], [1, 5, 50, 95, 99])
    s = samples.sort_values(["session_id", "t_utc"], kind="mergesort")
    dt = s.groupby("session_id")["t_utc"].diff().dt.total_seconds()
    d = haversine_m(s["lat"].shift(), s["lon"].shift(), s["lat"], s["lon"])
    speed = (d / dt)[dt > 0]
    c9 = log.set_index("rule").loc["C9"]
    excluded_frac = float(c9["rows_dropped"] / c9["rows_before"]) if c9["rows_before"] else 0.0
    frac_domain = float(contains_xy(domain, samples["lon"].to_numpy(), samples["lat"].to_numpy()).mean())
    checks = {
        "agl_p50_in_range": bool(g["agl_p50_range_m"][0] <= agl_q[2] <= g["agl_p50_range_m"][1]),
        "no_agl_below_min": bool((samples["agl_m"] >= g["min_retained_agl_m"]).all()),
        "speed_excluded_frac_ok": bool(excluded_frac <= g["max_speed_excluded_frac"]),
        "all_in_domain": frac_domain == 1.0,
        "dem_missing_zero": True,   # add_agl raises DemCoverageError otherwise, so reaching here means 0
    }
    return {
        "n_serials": int(samples["uas_id"].nunique()), "n_sessions": int(samples["session_id"].nunique()),
        "n_samples": int(len(samples)), "agl_p1_p5_p50_p95_p99_m": [round(float(v), 2) for v in agl_q],
        "speed_p50_p95_p99_mps": [round(float(v), 2) for v in np.percentile(speed, [50, 95, 99])] if len(speed) else None,
        "c9_excluded": int(c9["rows_dropped"]), "c9_excluded_frac": round(excluded_frac, 5),
        "frac_in_domain": round(frac_domain, 4), "frac_in_roi": round(float(samples["in_roi"].mean()), 4),
        "dem_missing": 0,
        "checks": checks, "failing": [k for k, v in checks.items() if not v],
        "G0": "PASS" if all(checks.values()) else "FAIL",
    }
