# Data

No personal data are distributed in this repository.

| Input | Where it goes | How to obtain |
|---|---|---|
| Drone tracks (Remote ID receptions, Interlagos, 2025) | `data/external/flights/raw/` | Not public: personal data provided under agreement. Drone-only pseudonymised tracks are not published. Access depends on the data provider's written authorisation. |
| Licensed cellular sites (SMP) | `data/external/anatel/` | Public ANATEL licensing records, cut with `data/external/anatel/cut_polygon.geojson`. The expected sha256 of the extract is in `experiments/configs/reference.yaml` (`stage_a.anatel_sha256`). Download from the ANATEL portal. |
| Terrain model | `data/external/terrain/` | Copernicus GLO-30 DEM crop around the venue. Check the Copernicus license terms. |
| Event geometry | `data/external/roi/` | Included (`roi.geojson`, `domain.geojson`) |

Operators appear as Operator A/B/C in all published outputs. The ANATEL records are public, so this avoids naming
operators but does not prevent re-identification from public data.
