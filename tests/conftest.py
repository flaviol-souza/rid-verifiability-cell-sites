"""Synthetic Stage A fixtures: no real data, no real key."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import rasterio
import yaml
from rasterio.transform import from_origin

REPO = Path(__file__).resolve().parents[1]
TEST_KEY_HEX = "00" * 31 + "01"            # test-only key, never a real one
DEM_ELEV_M = 750.0
LAT0, LON0 = -23.70, -46.70                # Interlagos-like, synthetic


def _square(lat0, lon0, half_deg):
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": {
        "type": "Polygon", "coordinates": [[[lon0 - half_deg, lat0 - half_deg], [lon0 + half_deg, lat0 - half_deg],
                                            [lon0 + half_deg, lat0 + half_deg], [lon0 - half_deg, lat0 + half_deg],
                                            [lon0 - half_deg, lat0 - half_deg]]]}}]}


def _ts(i):
    return (pd.Timestamp("2025-11-08T18:00:00Z") + pd.Timedelta(seconds=int(i))).strftime("%Y-%m-%dT%H:%M:%SZ")


HOME_ALT = DEM_ELEV_M + 6.0      # ground points sit ≈ 6 m above the DEM (audit N12)
OPER_ALT = DEM_ELEV_M + 7.0


def make_raw() -> pd.DataFrame:
    """Synthetic messages with the real file layout: up to three rows per (serial, second),
    1st = drone, 2nd = pilot/operator, 3rd = home."""
    rows = []
    pil = (LON0 - 0.0005, LAT0)
    home = (LON0 - 0.0005, LAT0 + 0.00002)

    def triple(sid, dlon, dlat, dalt, i):
        rows.append((sid, dlon, dlat, dalt, _ts(i)))
        rows.append((sid, pil[0], pil[1], HOME_ALT + 0.5, _ts(i)))
        rows.append((sid, home[0], home[1], HOME_ALT, _ts(i)))

    # SERIAL_A session 1: 5 m/s, but the position is logged in 10-s steps (held, then a 50-m jump)
    for i in range(120):
        triple("SERIAL_A", LON0 + (i // 10) * 10 * 0.00005, LAT0, 800.0, i)
    rows.insert(3 * 29 + 1, ("SERIAL_A", LON0 + 20 * 0.00005, LAT0, 800.0, _ts(29)))   # exact duplicate of the drone row → C1
    # SERIAL_A session 2 (after a 180-s gap): 1-s updates, one ~1 km GNSS spike → C9
    for i in range(300, 310):
        lon = LON0 + 0.0015 + (i - 300) * 0.00005
        if i == 305:
            lon += 0.01
        triple("SERIAL_A", lon, LAT0, 800.0, i)
    # SERIAL_C: drone + operator pairs (no home) → anchored on the ground reference
    for i in range(10):
        rows.append(("SERIAL_C", LON0 + 0.001, LAT0 + i * 0.00004, 800.0, _ts(i)))
        rows.append(("SERIAL_C", LON0 + 0.0012, LAT0, OPER_ALT, _ts(i)))
    # serial "encrypted": drone rows only → no anchor; literal id must still be pseudonymized
    for i in range(20):
        rows.append(("encrypted", LON0, LAT0 + i * 0.00004, 790.0, _ts(i)))
    # serial far away (other city) → C3
    for i in range(5):
        rows.append(("SERIAL_FAR", -45.87, -23.21, 605.0, _ts(i)))
    # placeholder: 50 identical rows (one timestamp, one position) → 49 go in C1, the serial goes in C4
    for _ in range(50):
        rows.append(("PLACEHOLDER", LON0, LAT0, 750.5, _ts(0)))
    # sentinel altitude → C5; low rows (AGL 2 m, no anchor) → C8
    rows.append(("SERIAL_B", LON0, LAT0, 2.0, _ts(0)))
    for i in range(1, 6):
        rows.append(("SERIAL_B", LON0, LAT0, 752.0, _ts(i)))
    for i in range(6, 12):
        rows.append(("SERIAL_B", LON0, LAT0 + i * 0.00003, 780.0, _ts(i)))
    return pd.DataFrame(rows, columns=["flight_id", "lon", "lat", "alt", "timestamp"])


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path
    (root / "data/external/flights/raw").mkdir(parents=True)
    (root / "data/external/anatel").mkdir(parents=True)
    (root / "data/external/terrain").mkdir(parents=True)
    (root / "data/external/roi").mkdir(parents=True)
    make_raw().to_csv(root / "data/external/flights/raw/utm_points_with_flightid.csv", index=False)
    pd.DataFrame({
        "Número Estação": ["1", "2", "3", "4"],
        "Latitude decimal": [str(LAT0), str(LAT0), str(LAT0 + 0.01), "-23.80"],
        "Longitude decimal": [str(LON0), str(LON0), str(LON0 + 0.01), "-46.80"],   # last one outside RoI and domain
        "Empresa Estação": ["OPB", "OPB", "OPA", "OPC"],
    }).to_csv(root / "data/external/anatel/Estacoes_SMP_interlagos.csv", sep=";", index=False)
    with rasterio.open(root / "data/external/terrain/glo30_interlagos_crop.tif", "w", driver="GTiff",
                       height=200, width=200, count=1, dtype="float32", crs="EPSG:4326",
                       transform=from_origin(LON0 - 0.1, LAT0 + 0.1, 0.001, 0.001)) as dst:
        dst.write(np.full((1, 200, 200), DEM_ELEV_M, dtype="float32"))
    (root / "data/external/roi/roi.geojson").write_text(json.dumps(_square(LAT0, LON0, 0.001)))
    (root / "data/external/roi/domain.geojson").write_text(json.dumps(_square(LAT0, LON0, 0.02)))
    cfg = yaml.safe_load((REPO / "experiments/configs/reference.yaml").read_text())
    import hashlib
    cfg["stage_a"]["anatel_sha256"] = hashlib.sha256(
        (root / cfg["stage_a"]["paths"]["anatel"]).read_bytes()).hexdigest()
    monkeypatch.setenv(cfg["stage_a"]["hmac_key_env"], TEST_KEY_HEX)
    return root, cfg
