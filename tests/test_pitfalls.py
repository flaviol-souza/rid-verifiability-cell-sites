"""Unit tests for the Section 4 pitfall statistics."""
import pandas as pd

from analysis.pitfalls import pitfall_stats


def test_pitfall_stats_known_values():
    t0 = pd.Timestamp("2025-11-08T12:00:00")
    rows = []
    # one flight: positions change every 20 s by 30 m; pilot 100 m away; each position repeated 3 times
    for i in range(6):
        for rep in range(3):
            rows.append(dict(flight="f", t=t0 + pd.Timedelta(seconds=20 * i + rep), x=30.0 * i, y=0.0, px=0.0, py=100.0))
    r = pitfall_stats(pd.DataFrame(rows))
    assert r["_n_flights"] == 1 and r["_n_speed_discarded"] == 0
    assert round(r["desc_hold_median_s"]) == 20 and round(r["desc_hold_jump_median_m"]) == 30
    assert r["desc_pilot_distance_median_m"] >= 100.0 and r["_pilot_found_share"] == 1.0


def test_pitfall_stats_counts_fast_jump():
    t0 = pd.Timestamp("2025-11-08T12:00:00")
    df = pd.DataFrame(dict(flight="f", t=[t0, t0 + pd.Timedelta(seconds=1)], x=[0.0, 500.0], y=0.0, px=0.0, py=0.0))
    assert pitfall_stats(df)["_n_speed_discarded"] == 1
