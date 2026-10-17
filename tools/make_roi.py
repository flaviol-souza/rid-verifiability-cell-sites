#!/usr/bin/env python3
"""BM-7 — Validate, (optionally) buffer, report and freeze the RoI polygon.

The polygon itself must come from a source INDEPENDENT of the evaluation data (see research.md, BM-7):
  A) the original RoI used in the 2026 version (≈ 5.29 km²), if its coordinates can be recovered;
  B) the Autódromo boundary from OpenStreetMap (exported with Overpass Turbo) plus a buffer chosen a priori.
Never derive it from the flight points of the evaluation (circular).

Usage:
  python tools/make_roi.py --input roi_source.geojson --buffer-m 0 --source "describe origin" \
     --flights data/external/flights/utm_points_with_flightid.csv \
     --sites data/external/anatel/Estacoes_SMP_interlagos.csv --rmax-m 1000 --out data/external/roi
Requires: shapely>=2, pyproj, pandas, numpy.
"""
import argparse, hashlib, json, datetime
from pathlib import Path
import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely.geometry import shape, mapping, Point, box
from shapely.ops import transform, unary_union

ap = argparse.ArgumentParser()
ap.add_argument("--input", required=True, help="GeoJSON (EPSG:4326) with one Polygon/MultiPolygon or a FeatureCollection")
ap.add_argument("--buffer-m", type=float, default=0.0, help="Buffer in metres; DS-v2 uses 0 (strict event boundary)")
ap.add_argument("--source", required=True, help="Free-text provenance, e.g. 'OSM way 123 via Overpass, accessed 2026-10-20'")
ap.add_argument("--flights", required=True)
ap.add_argument("--sites", required=True)
ap.add_argument("--rmax-m", type=float, default=1000.0, help="Candidate-site radius around the RoI (sites are NOT clipped to the RoI)")
ap.add_argument("--out", default="data/external/roi")
a = ap.parse_args()

gj = json.loads(Path(a.input).read_text())
geoms = [shape(f["geometry"]) for f in gj["features"]] if gj.get("type") == "FeatureCollection" else [shape(gj.get("geometry", gj))]
roi = unary_union(geoms)
assert roi.is_valid and roi.geom_type in ("Polygon", "MultiPolygon"), "invalid RoI geometry"

# Local metric projection (SIRGAS 2000 / UTM 23S covers São Paulo)
fwd = Transformer.from_crs("EPSG:4326", "EPSG:31983", always_xy=True).transform
inv = Transformer.from_crs("EPSG:31983", "EPSG:4326", always_xy=True).transform
roi_m = transform(fwd, roi)
if a.buffer_m:
    roi_m = roi_m.buffer(a.buffer_m)
roi = transform(inv, roi_m)
cand_m = roi_m.buffer(a.rmax_m)

fp = pd.read_csv(a.flights, dtype={"flight_id": str})
fp = fp[(fp.alt > 100) & (~fp.flight_id.isin(["1ZNBK5900C00A8", "MissionAlpha"]))].drop_duplicates(["flight_id", "timestamp"])
xy = [Point(fwd(x, y)) for x, y in zip(fp.lon, fp.lat)]
inside = np.array([roi_m.contains(p) for p in xy])

tw = pd.read_csv(a.sites, sep=";", dtype=str)
s = pd.DataFrame({"lat": pd.to_numeric(tw["Latitude decimal"].str.replace(",", ".")),
                  "lon": pd.to_numeric(tw["Longitude decimal"].str.replace(",", ".")),
                  "op": tw["Empresa Estação"]}).drop_duplicates(["lat", "lon"])
s_in = np.array([cand_m.contains(Point(fwd(x, y))) for x, y in zip(s.lon, s.lat)])

# Analysis domain: where the site inventory is complete within R_max.
# The ANATEL query area contains the bounding box of the returned sites, so eroding that box by R_max is conservative.
sx, sy = zip(*[fwd(x, y) for x, y in zip(s.lon, s.lat)])
dom_m = box(min(sx), min(sy), max(sx), max(sy)).buffer(-a.rmax_m, join_style=2)
assert not dom_m.is_empty, "analysis domain is empty: R_max too large for the site extract"
in_dom = np.array([dom_m.contains(p) for p in xy])
in_roi_and_dom = inside & in_dom
roi_in_dom = roi_m.intersection(dom_m).area / roi_m.area

report = {
    "source": a.source, "buffer_m": a.buffer_m, "rmax_m": a.rmax_m,
    "area_km2": round(roi_m.area / 1e6, 3),
    "flight_samples_inside_frac": round(float(inside.mean()), 4),
    "flight_samples_inside": int(inside.sum()), "flight_samples_total": int(len(inside)),
    "sites_within_rmax": int(s_in.sum()), "sites_total": int(len(s)),
    "domain_area_km2": round(dom_m.area / 1e6, 3),
    "flight_samples_in_domain": int(in_dom.sum()),
    "flight_samples_in_domain_frac": round(float(in_dom.mean()), 4),
    "flight_samples_in_roi_and_domain": int(in_roi_and_dom.sum()),
    "flight_samples_in_roi_and_domain_frac": round(float(in_roi_and_dom.mean()), 4),
    "roi_fraction_inside_domain": round(float(roi_in_dom), 4),
    "sites_within_rmax_by_operator": s[s_in].op.value_counts().to_dict(),
    "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
}
out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
geo = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "RoI", **report}, "geometry": mapping(roi)}]}
(out / "roi.geojson").write_text(json.dumps(geo, indent=1))
dom = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "analysis_domain",
       "definition": f"bbox of unique ANATEL sites eroded by R_max={a.rmax_m} m (inventory complete within R_max)"},
       "geometry": mapping(transform(inv, dom_m))}]}
(out / "domain.geojson").write_text(json.dumps(dom, indent=1))
report["sha256_roi_geojson"] = hashlib.sha256((out / "roi.geojson").read_bytes()).hexdigest()
report["sha256_domain_geojson"] = hashlib.sha256((out / "domain.geojson").read_bytes()).hexdigest()
(out / "roi_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
print(json.dumps(report, indent=1, ensure_ascii=False))
print("\nFreeze: commit roi.geojson + domain.geojson + roi_report.json + the original input file; cite the source in data/external/roi/README.md.")
