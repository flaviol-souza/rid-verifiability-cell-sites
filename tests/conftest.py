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


def make_raw() -> pd.DataFrame:
    rows = []
    # serial A: 120 s of normal flight (≈5 m/s), then a 180 s gap (new session), then 10 s more; one GNSS spike
    for i in range(120):
        rows.append(("SERIAL_A", LON0 + i * 0.00005, LAT0, 800.0, _ts(i)))
    rows.append(("SERIAL_A", LON0 + 29 * 0.00005, LAT0, 801.0, _ts(29)))            # same timestamp, other alt → C2
    rows.append(("SERIAL_A", LON0 + 29 * 0.00005, LAT0, 800.0, _ts(29)))            # exact duplicate → C1
    for i in range(300, 310):
        lon = LON0 + 0.0015 + (i - 300) * 0.00005
        if i == 305:
            lon += 0.01                                                              # ~1 km spike → C9
        rows.append(("SERIAL_A", lon, LAT0, 800.0, _ts(i)))
    # serial "encrypted": real flight, literal id must still be pseudonymized
    for i in range(20):
        rows.append(("encrypted", LON0, LAT0 + i * 0.00004, 790.0, _ts(i)))
    # serial far away (other city) → C3
    for i in range(5):
        rows.append(("SERIAL_FAR", -45.87, -23.21, 605.0, _ts(i)))
    # placeholder: 50 identical rows (one timestamp, one position) → 49 go in C1, the serial goes in C4
    for _ in range(50):
        rows.append(("PLACEHOLDER", LON0, LAT0, 750.5, _ts(0)))
    # sentinel altitude rows → C5; and low (AGL < 5 m) rows → C8
    rows.append(("SERIAL_B", LON0, LAT0, 2.0, _ts(0)))
    for i in range(1, 6):
        rows.append(("SERIAL_B", LON0, LAT0, 752.0, _ts(i)))                         # AGL 2 m → C8
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
        "Empresa Estação": ["CLARO", "CLARO", "VIVO", "TIM"],
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
