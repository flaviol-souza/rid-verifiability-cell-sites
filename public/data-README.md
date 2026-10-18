# Data

No personal data are distributed in this repository.

| Input | Where it goes | How to obtain |
|---|---|---|
| Drone tracks (Remote ID receptions, Interlagos, 2025) | `data/external/flights/raw/` | Not public: personal data provided under agreement. [FILL IN: drone-only pseudonymised tracks available / on request, after the provider's authorisation] |
| Licensed cellular sites (SMP) | `data/external/anatel/` | Public ANATEL licensing records, cut with `data/external/anatel/cut_polygon.geojson`. The expected sha256 of the extract is in `experiments/configs/reference.yaml` (`stage_a.anatel_sha256`). [FILL IN: download date and portal] |
| Terrain model | `data/external/terrain/` | [FILL IN: source and product, e.g. a Copernicus DEM crop around the venue; check its license terms] |
| Event geometry | `data/external/roi/` | Included (`roi.geojson`, `domain.geojson`) |

Operators appear as Operator A/B/C in all published outputs. The ANATEL records are public, so this avoids naming
operators but does not prevent re-identification from public data.
