import pandas as pd
import pytest

from analysis.descriptive import aggregate_descriptive


def test_descriptive_aggregations_are_time_weighted_and_paired():
    df = pd.DataFrame({
        "uas_id": ["u1", "u1", "u2"],
        "session_id": ["s1", "s2", "s3"],
        "dur_s": [90.0, 10.0, 100.0],
        "heard": [1.0, 0.0, 0.5],
        "v3": [0.8, 0.0, 0.1],
    })
    out, drones = aggregate_descriptive(df)
    assert out["total_flight_time_s"] == 200.0
    assert out["median_session_duration_s"] == 90.0
    assert out["heard_pooled"] == pytest.approx(0.7)
    assert out["v3_pooled"] == pytest.approx(0.41)
    assert out["gap_pooled"] == pytest.approx(0.29)
    assert out["dominant_time_share"] == pytest.approx(0.5)
    assert out["dominant_v3"] == pytest.approx(0.72)
    assert out["v3_leave_dominant_out"] == pytest.approx(0.1)
    assert out["heard_leave_dominant_out"] == pytest.approx(0.5)
    assert out["gap_leave_dominant_out"] == pytest.approx(0.4)
    assert out["n_drones_v3_below_0_5"] == 1
    assert drones.set_index("uas_id").loc["u1", "v3"] == pytest.approx(0.72)
    assert out["gap_per_drone_mean"] == pytest.approx(out["heard_per_drone_mean"] - out["v3_per_drone_mean"])
