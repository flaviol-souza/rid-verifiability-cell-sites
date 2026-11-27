"""BM-2 / T1 sanity check: sample the frozen DEM at cell sites and flight samples, and compare
DEM ground with the per-session proxy (2nd percentile of session altitude).

Usage: python tools/check_terrain.py --dem data/external/terrain/glo30_interlagos_crop.tif \
         --flights data/external/flights/utm_points_with_flightid.csv \
         --sites data/external/anatel/Estacoes_SMP_interlagos.csv
Requires: rasterio, pandas, numpy.
"""
import argparse
import numpy as np
import pandas as pd
import rasterio

ap = argparse.ArgumentParser()
ap.add_argument("--dem", required=True)
ap.add_argument("--flights", required=True)
ap.add_argument("--sites", required=True)
ap.add_argument("--session-gap-s", type=float, default=60.0)
a = ap.parse_args()

def sample(src, lon, lat):
    vals = np.array([v[0] for v in src.sample(zip(lon, lat))], dtype=float)
    if src.nodata is not None:
        vals[vals == src.nodata] = np.nan
    return vals

with rasterio.open(a.dem) as src:
    print("DEM CRS:", src.crs, "| nodata:", src.nodata, "| bounds:", src.bounds)

    tw = pd.read_csv(a.sites, sep=";", dtype=str)
    lat = pd.to_numeric(tw["Latitude decimal"].str.replace(",", "."))
    lon = pd.to_numeric(tw["Longitude decimal"].str.replace(",", "."))
    sites = pd.DataFrame({"lat": lat, "lon": lon}).drop_duplicates()
    sites["dem_m"] = sample(src, sites.lon, sites.lat)
    print(f"\nSites: {len(sites)} | DEM elevation p5/p50/p95 (m): {np.nanpercentile(sites.dem_m, [5, 50, 95]).round(1)}"
          f" | missing: {sites.dem_m.isna().sum()}")

    fp = pd.read_csv(a.flights, dtype={"flight_id": str})
    fp["timestamp"] = pd.to_datetime(fp["timestamp"], utc=True)
    # Rule-based (no serial literals in tracked code): serials never inside the site bbox, and placeholders.
    in_box = (fp.lat.between(sites.lat.min(), sites.lat.max()) & fp.lon.between(sites.lon.min(), sites.lon.max())).to_numpy(dtype=bool)
    g = fp.groupby("flight_id")
    placeholder = (g.timestamp.transform("nunique") == 1) & (g.lat.transform("nunique") == 1) & (g.lon.transform("nunique") == 1)
    fp = fp[(fp.alt > 100) & fp.flight_id.isin(set(fp.flight_id[in_box])) & ~placeholder]
    fp = fp.drop_duplicates(["flight_id", "timestamp"]).sort_values(["flight_id", "timestamp"])
    gap = fp.groupby("flight_id").timestamp.diff().dt.total_seconds()
    fp["session"] = fp.flight_id + "_" + (gap > a.session_gap_s).groupby(fp.flight_id).cumsum().astype(str)
    fp["dem_m"] = sample(src, fp.lon, fp.lat)
    fp["agl_dem_m"] = fp.alt - fp.dem_m
    fp["agl_proxy_m"] = fp.alt - fp.groupby("session").alt.transform(lambda s: np.percentile(s, 2))

print(f"\nFlight samples: {len(fp)} | sessions: {fp.session.nunique()} | DEM missing: {fp.dem_m.isna().sum()}")
print("AGL (DEM)   p1/p5/p50/p95/p99 (m):", np.nanpercentile(fp.agl_dem_m, [1, 5, 50, 95, 99]).round(1))
print("AGL (proxy) p1/p5/p50/p95/p99 (m):", np.nanpercentile(fp.agl_proxy_m, [1, 5, 50, 95, 99]).round(1))
d = (fp.agl_dem_m - fp.agl_proxy_m)
print("DEM − proxy difference p5/p50/p95 (m):", np.nanpercentile(d, [5, 50, 95]).round(1))
neg = (fp.agl_dem_m < -5).mean()
print(f"Fraction with AGL(DEM) < −5 m: {neg:.3f}  <- if large, suspect a datum mismatch (HAE vs EGM2008) or DSM over buildings")
print("\nT1 pass criteria (methods.md): retained AGL within [−5, 500] m; investigate any systematic offset before freezing.")
