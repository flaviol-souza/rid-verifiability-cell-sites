"""Stage A orchestration and G0 evaluation. Rules version v2 (methods.md, deviation log G0-v1 → v2)."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from shapely.geometry import box, shape

from drs.data import agl, anonymize, clean, sites

SAMPLE_COLS = ["sample_id", "session_id", "uas_id", "t_utc", "lat", "lon", "agl_m", "agl_dem_m",
               "agl_anchor", "group_size", "in_roi"]
REF_COLS = ["uas_id", "session_id", "t_utc", "role", "group_size", "lat", "lon", "agl_dem_m"]


class InputHashMismatch(RuntimeError):
    pass


def _geom(path):
    gj = json.loads(Path(path).read_text())
    return shape(gj["features"][0]["geometry"] if "features" in gj else gj)


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_config(path="experiments/configs/reference.yaml") -> dict:
    return yaml.safe_load(Path(path).read_text())


def _site_extent(site_tab: pd.DataFrame):
    return box(site_tab["lon"].min(), site_tab["lat"].min(), site_tab["lon"].max(), site_tab["lat"].max())


def run(cfg: dict, root: Path = Path(".")) -> dict:
    a, p = cfg["stage_a"], {k: root / v for k, v in cfg["stage_a"]["paths"].items()}
    key = anonymize.load_key(a["hmac_key_env"])                       # fails before any output
    if a.get("anatel_sha256") and sha256(p["anatel"]) != a["anatel_sha256"]:
        raise InputHashMismatch(f"ANATEL extract hash {sha256(p['anatel'])} != config {a['anatel_sha256']}")
    site_tab = sites.collapse_sites(pd.read_csv(p["anatel"], sep=";", dtype=str))
    raw = pd.read_csv(p["flights_raw"], dtype={"flight_id": str})
    flights = anonymize.anonymize_flights(raw, key, a["pseudonym_prefix"], a["pseudonym_hex_chars"])

    df = flights.rename(columns={"timestamp": "t_utc"})
    df["t_utc"] = pd.to_datetime(df["t_utc"], utc=True)
    domain, roi, extent = _geom(p["domain"]), _geom(p["roi"]), _site_extent(site_tab)
    log = clean.CleaningLog()
    refs_holder = {}

    def c2(d):
        drone, refs = clean.c2_split_roles(d)
        refs_holder["refs"] = refs
        return drone

    steps = [("C1", clean.c1_exact_duplicates), ("C2", c2),
             ("C3", lambda d: clean.c3_outside_extent(d, extent)), ("C4", clean.c4_placeholders),
             ("C5", lambda d: clean.c5_sentinel_altitude(d, a["sentinel_min_alt_msl_m"])),
             ("C6", lambda d: clean.c6_sessionize(d, a["session_gap_s"])),
             ("C7", lambda d: agl.add_agl(d, str(p["dem"]), _refs_for(d, refs_holder["refs"], a))),
             ("C8", lambda d: clean.c8_domain_and_roi(d, domain, roi, a["min_agl_m"])),
             ("C9", lambda d: clean.c9_speed(d, a["max_ground_speed_mps"], a["c9_estimator"]))]
    snap = {}
    for name, fn in steps:
        new = fn(df)
        log.record(name, df, new)
        snap[name] = new
        if name == "C2":
            _publish_drone_track(new, p, a)
        df = new

    # diagnostics that never change the pipeline
    pre_c9 = snap["C8"]
    c9_alt = "consecutive" if a["c9_estimator"] == "since_first_seen" else "since_first_seen"
    c9_alt_excluded = len(pre_c9) - len(clean.c9_speed(pre_c9, a["max_ground_speed_mps"], c9_alt))
    refs_sess = _refs_for(snap["C6"], refs_holder["refs"], a)
    _, refs_agl = agl.anchor_offsets(refs_sess, str(p["dem"]))
    role_consistency = _role_consistency(snap["C7"], refs_agl)

    df = df.sort_values(["session_id", "t_utc"], kind="mergesort").reset_index(drop=True)
    df.insert(0, "sample_id", np.arange(len(df)))
    samples = df[SAMPLE_COLS]
    ground_refs = (refs_agl[REF_COLS].sort_values(["session_id", "t_utc", "role"], kind="mergesort")
                   .reset_index(drop=True) if refs_agl is not None and len(refs_agl) else pd.DataFrame(columns=REF_COLS))

    out = p["interim_dir"]; out.mkdir(parents=True, exist_ok=True)
    samples.to_parquet(out / "samples.parquet", index=False)
    ground_refs.to_parquet(out / "ground_refs.parquet", index=False)   # pilot/home positions: never published
    site_tab.to_parquet(out / "sites.parquet", index=False)
    log.to_frame().to_csv(out / "cleaning_log.csv", index=False, lineterminator="\n")
    return {"samples": samples, "sites": site_tab, "log": log.to_frame(), "domain": domain,
            "ground_refs": ground_refs, "refs_all": refs_holder["refs"],
            "diag": {"c9_estimator": a["c9_estimator"], "c9_alt_estimator": c9_alt,
                     "c9_alt_excluded": int(c9_alt_excluded), "role_consistency": role_consistency}}


def _refs_for(drone_sessions: pd.DataFrame, refs: pd.DataFrame, a: dict) -> pd.DataFrame:
    """Attach session_id to ground references through the drone row of the same message.
    Refs whose drone row was removed by C3–C5, and refs with sentinel altitudes, are dropped."""
    key = drone_sessions[["uas_id", "t_utc", "session_id"]]
    r = refs[refs["alt"] >= a["sentinel_min_alt_msl_m"]].merge(key, on=["uas_id", "t_utc"], how="inner")
    return r.reset_index(drop=True)


def _role_consistency(drone_c7: pd.DataFrame, refs_agl: pd.DataFrame) -> float | None:
    """Fraction of messages (with a 2nd position) where the 1st position is higher above the DEM than the 2nd."""
    if refs_agl is None or refs_agl.empty:
        return None
    second = refs_agl[refs_agl["role"].isin(["pilot", "ground_ref"])][["uas_id", "t_utc", "agl_dem_m"]]
    m = drone_c7[["uas_id", "t_utc", "agl_dem_m"]].merge(second, on=["uas_id", "t_utc"], suffixes=("_1", "_2"))
    return round(float((m["agl_dem_m_1"] > m["agl_dem_m_2"]).mean()), 4) if len(m) else None


def _publish_drone_track(drone: pd.DataFrame, p: dict, a: dict) -> None:
    """Published file: drone positions only (roles listed in publish_roles). Pilot and home positions are
    personal data and stay in data/interim (git-ignored)."""
    if a.get("publish_roles", ["drone"]) != ["drone"]:
        raise ValueError("only the drone track may be published (pilot/home positions are personal data)")
    pub = drone[["uas_id", "lon", "lat", "alt", "t_utc"]].copy()
    pub["timestamp"] = pub.pop("t_utc").dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    p["flights_anon"].parent.mkdir(parents=True, exist_ok=True)
    pub.to_csv(p["flights_anon"], index=False, lineterminator="\n")
    p["flights_anon"].with_suffix(".sha256").write_text(f"{sha256(p['flights_anon'])}  {p['flights_anon'].name}\n")


def g0_evaluate(samples: pd.DataFrame, log: pd.DataFrame, cfg: dict, domain, diag: dict | None = None) -> dict:
    """G0 (research.md). Criteria come only from cfg['g0']; never edit them after seeing data."""
    from shapely import contains_xy
    g, a = cfg["g0"], cfg["stage_a"]
    diag = diag or {}
    agl_q = np.percentile(samples["agl_m"], [1, 5, 50, 95, 99])
    s = samples.sort_values(["session_id", "t_utc"], kind="mergesort").reset_index(drop=True)
    speed = clean.implied_speeds(s, a["c9_estimator"])
    speed = speed[np.isfinite(speed)]
    c9 = log.set_index("rule").loc["C9"]
    excluded_frac = float(c9["rows_dropped"] / c9["rows_before"]) if c9["rows_before"] else 0.0
    frac_domain = float(contains_xy(domain, samples["lon"].to_numpy(), samples["lat"].to_numpy()).mean())
    anchors = samples.drop_duplicates("session_id")["agl_anchor"].value_counts().to_dict()
    rc = diag.get("role_consistency")
    checks = {
        "agl_p50_in_range": bool(g["agl_p50_range_m"][0] <= agl_q[2] <= g["agl_p50_range_m"][1]),
        "no_agl_below_min": bool((samples["agl_m"] >= g["min_retained_agl_m"]).all()),
        "speed_excluded_frac_ok": bool(excluded_frac <= g["max_speed_excluded_frac"]),
        "all_in_domain": frac_domain == 1.0,
        "dem_missing_zero": True,   # add_agl raises DemCoverageError otherwise, so reaching here means 0
        "role_consistency_ok": rc is not None and rc >= g["min_role_consistency"],
    }
    return {
        "rules_version": a.get("rules_version", "v2"),
        "n_serials": int(samples["uas_id"].nunique()), "n_sessions": int(samples["session_id"].nunique()),
        "n_samples": int(len(samples)), "agl_p1_p5_p50_p95_p99_m": [round(float(v), 2) for v in agl_q],
        "agl_dem_p50_m": round(float(np.median(samples["agl_dem_m"])), 2),
        "sessions_by_anchor": {k: int(v) for k, v in sorted(anchors.items())},
        "frac_samples_group_size_1": round(float((samples["group_size"] == 1).mean()), 4),
        "speed_estimator": a["c9_estimator"],
        "speed_p50_p95_p99_mps": [round(float(v), 2) for v in np.percentile(speed, [50, 95, 99])] if len(speed) else None,
        "c9_excluded": int(c9["rows_dropped"]), "c9_excluded_frac": round(excluded_frac, 5),
        "c9_excluded_with_alt_estimator_diag": diag.get("c9_alt_excluded"),
        "role_consistency": rc,
        "frac_in_domain": round(frac_domain, 4), "frac_in_roi": round(float(samples["in_roi"].mean()), 4),
        "dem_missing": 0,
        "checks": checks, "failing": [k for k, v in checks.items() if not v],
        "G0": "PASS" if all(checks.values()) else "FAIL",
    }
