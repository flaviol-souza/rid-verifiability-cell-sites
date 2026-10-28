"""Descriptive time and drone aggregations; no hypothesis tests."""
from __future__ import annotations

import pandas as pd


def _weighted(group: pd.DataFrame, column: str) -> float:
    return float((group[column] * group["dur_s"]).sum() / group["dur_s"].sum())


def aggregate_descriptive(frame: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """Aggregate paired heard/V3 fractions from one row per flight/session.

    Each drone's value is the duration-weighted mean over its flights. The
    per-drone aggregate then gives every drone equal weight.
    """
    required = {"uas_id", "session_id", "dur_s", "heard", "v3"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"missing descriptive columns: {sorted(missing)}")
    if frame.empty or (frame["dur_s"] <= 0).any():
        raise ValueError("descriptive input must contain positive flight durations")

    rows = []
    for uas_id, group in frame.groupby("uas_id", sort=True):
        rows.append({
            "uas_id": uas_id,
            "dur_s": float(group["dur_s"].sum()),
            "n_sessions": int(group["session_id"].nunique()),
            "heard": _weighted(group, "heard"),
            "v3": _weighted(group, "v3"),
        })
    drones = pd.DataFrame(rows)
    drones["gap"] = drones["heard"] - drones["v3"]
    dominant = drones.sort_values(["dur_s", "uas_id"], ascending=[False, True]).iloc[0]
    remaining = frame[frame["uas_id"] != dominant["uas_id"]]

    heard_pooled = _weighted(frame, "heard")
    v3_pooled = _weighted(frame, "v3")
    out = {
        "descriptive": True,
        "n_sessions": int(frame["session_id"].nunique()),
        "n_drones": int(frame["uas_id"].nunique()),
        "total_flight_time_s": float(frame["dur_s"].sum()),
        "median_session_duration_s": float(frame["dur_s"].median()),
        "heard_pooled": heard_pooled,
        "v3_pooled": v3_pooled,
        "gap_pooled": heard_pooled - v3_pooled,
        "heard_per_drone_mean": float(drones["heard"].mean()),
        "v3_per_drone_mean": float(drones["v3"].mean()),
        "gap_per_drone_mean": float(drones["gap"].mean()),
        "dominant_uas_id": dominant["uas_id"],
        "dominant_time_share": float(dominant["dur_s"] / frame["dur_s"].sum()),
        "dominant_v3": float(dominant["v3"]),
        "n_drones_v3_below_0_5": int((drones["v3"] < 0.5).sum()),
    }
    if remaining.empty:
        out.update({
            "heard_leave_dominant_out": float("nan"),
            "v3_leave_dominant_out": float("nan"),
            "gap_leave_dominant_out": float("nan"),
        })
    else:
        heard_loo = _weighted(remaining, "heard")
        v3_loo = _weighted(remaining, "v3")
        out.update({
            "heard_leave_dominant_out": heard_loo,
            "v3_leave_dominant_out": v3_loo,
            "gap_leave_dominant_out": heard_loo - v3_loo,
        })
    return out, drones


def tables_from_pipeline(metrics: pd.DataFrame, samples: pd.DataFrame, gap_cap_s: float,
                         family: str, ranges_m=(100.0, 200.0)) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build descriptive aggregates after averaging seeds, from the same sample-time basis as H2."""
    from analysis.observability import time_weights_s

    weights = time_weights_s(samples, gap_cap_s)
    durations = (samples.assign(dur_s=weights)
                 .groupby(["session_id", "uas_id"], as_index=False)["dur_s"].sum())
    rows, drone_rows = [], []
    scenarios = sorted(metrics.loc[metrics["family"] == family, "scenario"].unique())
    for scenario in scenarios:
        for range_m in ranges_m:
            selected = metrics[(metrics["family"] == family) & (metrics["scenario"] == scenario)
                               & (metrics["range_m"] == float(range_m))
                               & metrics["metric"].isin(["observable_k1", "V3_D100"])]
            averaged = selected.groupby(["session_id", "uas_id", "metric"], as_index=False)["value"].mean()
            wide = averaged.pivot(index=["session_id", "uas_id"], columns="metric", values="value").reset_index()
            if not {"observable_k1", "V3_D100"} <= set(wide):
                continue
            frame = wide.merge(durations, on=["session_id", "uas_id"], validate="one_to_one").rename(
                columns={"observable_k1": "heard", "V3_D100": "v3"})
            summary, drones = aggregate_descriptive(frame)
            summary.update({"family": family, "scenario": scenario, "range_m": float(range_m),
                            "metric_definition": "descriptive; seeds averaged before time aggregation"})
            rows.append(summary)
            drones.insert(0, "range_m", float(range_m)); drones.insert(0, "scenario", scenario)
            drones.insert(0, "family", family); drone_rows.append(drones)
    return pd.DataFrame(rows), pd.concat(drone_rows, ignore_index=True)
