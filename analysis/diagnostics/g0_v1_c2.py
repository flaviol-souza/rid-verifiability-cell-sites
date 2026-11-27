"""Read-only C2/C9 diagnostics for G0-v1.

Inputs are the anonymized flight log after C1/C3 filtering and the frozen
ANATEL domain/DEM. Outputs are diagnostic CSVs only; Stage A is not changed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import yaml
from shapely import contains_xy
from shapely.geometry import shape

from drs.geo import haversine_m


def load_geometry(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    return shape(payload["features"][0]["geometry"])


def add_agl(frame: pd.DataFrame, dem_path: Path) -> pd.DataFrame:
    with rasterio.open(dem_path) as src:
        elevation = np.array(
            [value[0] for value in src.sample(zip(frame["lon"], frame["lat"]))],
            dtype=float,
        )
    out = frame.copy()
    out["agl_m"] = out["alt"] - elevation
    return out


def sessionize(frame: pd.DataFrame, gap_s: float) -> pd.DataFrame:
    out = frame.sort_values(["uas_id", "t_utc", "file_order"], kind="mergesort").copy()
    gaps = out.groupby("uas_id")["t_utc"].diff().dt.total_seconds()
    out["session_id"] = out["uas_id"] + "_s" + (
        (gaps > gap_s).groupby(out["uas_id"]).cumsum().astype(int).map("{:03d}".format)
    )
    return out


def speed_summary(frame: pd.DataFrame, method: str, vmax_mps: float) -> dict:
    speeds = []
    excluded = 0
    for _, group in frame.groupby("session_id", sort=False):
        group = group.sort_values(["t_utc", "file_order"], kind="mergesort")
        previous_position = None
        previous_time = None
        previous_position_first_time = None
        for row in group.itertuples(index=False):
            position = (float(row.lat), float(row.lon))
            if method == "consecutive":
                reference_position = previous_position
                reference_time = previous_time
            else:
                reference_position = previous_position
                reference_time = previous_position_first_time
            if reference_position is not None:
                dt = (row.t_utc - reference_time).total_seconds()
                distance = haversine_m(reference_position[0], reference_position[1], row.lat, row.lon)
                speed = distance / dt if dt > 0 else np.inf
                speeds.append(speed)
                if speed > vmax_mps:
                    excluded += 1
            if previous_position != position:
                previous_position = position
                previous_position_first_time = row.t_utc
            previous_time = row.t_utc
    values = np.asarray(speeds, dtype=float)
    return {
        "method": method,
        "steps": int(values.size),
        "excluded_over_vmax": int(excluded),
        "excluded_fraction": round(float(excluded / len(frame)), 6),
        "speed_p50_mps": round(float(np.percentile(values, 50)), 3) if values.size else None,
        "speed_p95_mps": round(float(np.percentile(values, 95)), 3) if values.size else None,
        "speed_p99_mps": round(float(np.percentile(values, 99)), 3) if values.size else None,
        "max_speed_mps": round(float(np.max(values)), 3) if values.size else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="experiments/configs/reference.yaml")
    parser.add_argument("--output", default="results/g0_data/20261016T193702Z/diag")
    args = parser.parse_args()
    root = Path(__file__).parents[2]
    config = yaml.safe_load((root / args.config).read_text(encoding="utf-8"))
    stage = config["stage_a"]
    paths = {name: root / value for name, value in stage["paths"].items()}
    out_dir = root / args.output
    out_dir.mkdir(parents=True, exist_ok=True)

    frame = pd.read_csv(paths["flights_anon"], dtype={"uas_id": str})
    frame["file_order"] = np.arange(len(frame))
    frame["t_utc"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.rename(columns={"flight_id": "uas_id"}) if "flight_id" in frame else frame

    # C1 then C3, deliberately before C2.
    frame = frame.drop_duplicates(keep="first").reset_index(drop=True)
    domain = load_geometry(paths["domain"])
    in_domain = contains_xy(domain, frame["lon"].to_numpy(), frame["lat"].to_numpy())
    keep_uas = set(frame.loc[in_domain, "uas_id"])
    frame = frame[frame["uas_id"].isin(keep_uas)].reset_index(drop=True)
    frame = add_agl(frame, paths["dem"])
    frame = sessionize(frame, float(stage["session_gap_s"]))

    duplicate_groups = frame.groupby(["uas_id", "t_utc"], sort=False)
    group_rows = []
    ordinal_rows = []
    for (uas_id, timestamp), group in duplicate_groups:
        if len(group) != 3:
            continue
        group = group.sort_values("file_order", kind="mergesort").reset_index(drop=True)
        distances = [
            haversine_m(group.loc[i, "lat"], group.loc[i, "lon"], group.loc[i + 1, "lat"], group.loc[i + 1, "lon"])
            for i in range(2)
        ]
        group_rows.append({
            "uas_id": uas_id,
            "t_utc": timestamp,
            "session_id": group.loc[0, "session_id"],
            "distance_1_to_2_m": round(float(distances[0]), 6),
            "distance_2_to_3_m": round(float(distances[1]), 6),
            "distance_1_to_3_m": round(float(haversine_m(group.loc[0, "lat"], group.loc[0, "lon"], group.loc[2, "lat"], group.loc[2, "lon"])), 6),
        })
        for ordinal, row in group.iterrows():
            ordinal_rows.append({
                "uas_id": uas_id,
                "t_utc": timestamp,
                "session_id": row.session_id,
                "ordinal": ordinal + 1,
                "lat": row.lat,
                "lon": row.lon,
                "agl_m": row.agl_m,
                "position_key": f"{row.lat:.7f},{row.lon:.7f}",
            })

    groups = pd.DataFrame(group_rows)
    ordinals = pd.DataFrame(ordinal_rows)
    if groups.empty:
        groups = pd.DataFrame(columns=["uas_id", "t_utc", "session_id", "distance_1_to_2_m", "distance_2_to_3_m", "distance_1_to_3_m"])
    if ordinals.empty:
        ordinals = pd.DataFrame(columns=["uas_id", "t_utc", "session_id", "ordinal", "lat", "lon", "agl_m", "position_key"])
    groups.to_csv(out_dir / "duplicate_triples.csv", index=False, lineterminator="\n")
    ordinals.to_csv(out_dir / "duplicate_triple_positions.csv", index=False, lineterminator="\n")

    ordinal_summary = []
    for ordinal, group in ordinals.groupby("ordinal"):
        zero_fraction = float((group["position_key"] == group["position_key"].shift()).mean()) if len(group) > 1 else 0.0
        ordinal_summary.append({
            "ordinal": int(ordinal),
            "rows": int(len(group)),
            "zero_displacement_fraction": round(zero_fraction, 6),
            "agl_p50_m": round(float(group["agl_m"].median()), 6) if len(group) else None,
        })
    frame["position_key"] = frame.apply(lambda row: f"{row.lat:.7f},{row.lon:.7f}", axis=1)
    position_frame = frame.sort_values(["session_id", "t_utc", "file_order"], kind="mergesort").copy()
    position_frame["next_t_utc"] = position_frame.groupby("session_id")["t_utc"].shift(-1)
    position_frame["duration_s"] = (position_frame["next_t_utc"] - position_frame["t_utc"]).dt.total_seconds().clip(lower=0).fillna(0)
    session_duration = position_frame.groupby("session_id")["duration_s"].sum()
    fixed_duration = position_frame.groupby(["session_id", "position_key"])["duration_s"].sum()
    if not ordinals.empty:
        ordinals["fixed_fraction"] = [
            float(fixed_duration.get((session_id, position_key), 0.0) / session_duration.get(session_id, 1.0))
            for session_id, position_key in zip(ordinals["session_id"], ordinals["position_key"])
        ]
        fixed_by_ordinal = ordinals.groupby("ordinal")["fixed_fraction"].mean().to_dict()
    else:
        fixed_by_ordinal = {}
    for row in ordinal_summary:
        row["fixed_time_fraction_mean"] = round(float(fixed_by_ordinal.get(row["ordinal"], 0.0)), 6)
    pd.DataFrame(ordinal_summary).to_csv(out_dir / "duplicate_triple_ordinal_summary.csv", index=False, lineterminator="\n")

    extra_rows = []
    complete_groups = duplicate_groups.filter(lambda group: len(group) == 3)
    home_by_session = {}
    for session_id, complete in complete_groups.groupby("session_id"):
        third = complete.sort_values("file_order").groupby(["session_id", "t_utc"], sort=False).nth(2)
        if len(third):
            mode = third[["lat", "lon"]].round(7).mode().iloc[0]
            home_by_session[session_id] = (float(mode["lat"]), float(mode["lon"]))
    complete_times = {
        session_id: sorted(group["t_utc"].unique())
        for session_id, group in complete_groups.groupby("session_id")
    }
    c8_all = contains_xy(domain, frame["lon"].to_numpy(), frame["lat"].to_numpy()) & (frame["agl_m"].to_numpy() > float(stage["min_agl_m"]))
    frame["c8_keep"] = c8_all
    complete_keys = set((row.uas_id, row.t_utc) for row in groups.itertuples(index=False))
    c8_complete = frame.apply(lambda row: row.c8_keep and (row.uas_id, row.t_utc) in complete_keys, axis=1)
    for (uas_id, timestamp), group in duplicate_groups:
        if len(group) not in (1, 2):
            continue
        session_id = group.iloc[0]["session_id"]
        complete_timestamps = complete_times.get(session_id, [])
        if not complete_timestamps:
            relation = "no_complete_group"
        elif timestamp < complete_timestamps[0]:
            relation = "before_first_complete"
        elif timestamp > complete_timestamps[-1]:
            relation = "after_last_complete"
        else:
            relation = "between_complete_groups"
        home = home_by_session.get(session_id)
        for ordinal, row in group.sort_values("file_order").reset_index(drop=True).iterrows():
            distance = None if home is None else haversine_m(home[0], home[1], row.lat, row.lon)
            extra_rows.append({
                "uas_id": uas_id,
                "t_utc": timestamp,
                "session_id": session_id,
                "group_size": len(group),
                "ordinal": ordinal + 1,
                "agl_m": round(float(row.agl_m), 6),
                "home_distance_m": None if distance is None else round(float(distance), 6),
                "relative_to_complete_groups": relation,
                "c8_keep": bool(row.c8_keep),
            })
    pd.DataFrame(extra_rows).to_csv(out_dir / "incomplete_group_positions.csv", index=False, lineterminator="\n")
    pd.DataFrame([{
        "c8_samples_all_groups": int(c8_all.sum()),
        "c8_samples_complete_groups_only": int(c8_complete.sum()),
        "c8_samples_incomplete_groups": int(c8_all.sum() - c8_complete.sum()),
    }]).to_csv(out_dir / "c8_complete_vs_all.csv", index=False, lineterminator="\n")

    c2 = frame.drop_duplicates(["uas_id", "t_utc"], keep="first").reset_index(drop=True)
    c2 = sessionize(c2, float(stage["session_gap_s"]))
    pd.DataFrame([
        speed_summary(c2, "consecutive", float(stage["max_ground_speed_mps"])),
        speed_summary(c2, "previous_position_first_seen", float(stage["max_ground_speed_mps"])),
    ]).to_csv(out_dir / "c9_estimator_comparison.csv", index=False, lineterminator="\n")

    pd.DataFrame([{
        "c1_c3_rows": len(frame),
        "c1_c3_uas": frame["uas_id"].nunique(),
        "duplicate_timestamp_groups_size_3": len(groups),
        "c2_rows": len(c2),
        "c2_sessions": c2["session_id"].nunique(),
    }]).to_csv(out_dir / "diagnostic_summary.csv", index=False, lineterminator="\n")


if __name__ == "__main__":
    main()
