"""Determinism and provenance tests for the frozen RoI generator."""
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]
GENERATOR = REPOSITORY_ROOT / "tools" / "make_roi.py"


def _write_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    source = tmp_path / "osm_autodromo.geojson"
    source.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"osm_type": "relation", "osm_id": 2560355},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [-46.70, -23.70],
                                    [-46.69, -23.70],
                                    [-46.69, -23.69],
                                    [-46.70, -23.69],
                                    [-46.70, -23.70],
                                ]
                            ],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    flights = tmp_path / "flights.csv"
    flights.write_text(
        "flight_id,timestamp,alt,lon,lat\n"
        "uas-original,2026-01-01T00:00:00Z,150,-46.695,-23.695\n",
        encoding="utf-8",
    )
    sites = tmp_path / "sites.csv"
    sites.write_text(
        "Latitude decimal;Longitude decimal;Empresa Estação\n"
        "-23.695;-46.695;TEST\n"
        "-23.695;-46.685;TEST\n"
        "-23.685;-46.695;TEST\n"
        "-23.685;-46.685;TEST\n",
        encoding="utf-8",
    )
    return source, flights, sites


def _run_generator(tmp_path: Path, source: Path, flights: Path, sites: Path, output: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--input",
            str(source),
            "--buffer-m",
            "0",
            "--source",
            "OSM relation 2560355",
            "--flights",
            str(flights),
            "--sites",
            str(sites),
            "--rmax-m",
            "100",
            "--out",
            str(output),
        ],
        check=True,
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_make_roi_is_deterministic_and_preserves_source_geometry(tmp_path: Path) -> None:
    """Repeated generation has stable bytes and preserves rounded source coordinates."""
    source, flights, sites = _write_inputs(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"
    _run_generator(tmp_path, source, flights, sites, first)
    time.sleep(1.1)
    _run_generator(tmp_path, source, flights, sites, second)

    assert _sha256(first / "roi.geojson") == _sha256(second / "roi.geojson")
    assert _sha256(first / "domain.geojson") == _sha256(second / "domain.geojson")
    first_report = json.loads((first / "roi_report.json").read_text(encoding="utf-8"))
    second_report = json.loads((second / "roi_report.json").read_text(encoding="utf-8"))
    assert first_report["created_utc"] != second_report["created_utc"]

    source_geometry = json.loads(source.read_text(encoding="utf-8"))["features"][0]["geometry"]
    generated = json.loads((first / "roi.geojson").read_text(encoding="utf-8"))
    properties = generated["features"][0]["properties"]
    assert properties["osm_type"] == "relation"
    assert properties["osm_id"] == 2560355
    assert generated["features"][0]["geometry"] == source_geometry
