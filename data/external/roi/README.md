# Interlagos RoI and analysis domain

## Event RoI

The event RoI is the strict, unbuffered boundary of the Autódromo José Carlos Pace. It is independent of the flight observations and is used as a secondary event-area stratum and for the scenario figure. It is not used to filter the main flight sample set.

- Source: OpenStreetMap relation `2560355`, `Autódromo José Carlos Pace`.
- OSM geometry endpoint used for the saved polygon: Nominatim object lookup, accessed 2026-10-16.
- Exact URL: `https://nominatim.openstreetmap.org/lookup?osm_ids=R2560355&format=geojson&polygon_geojson=1`.
- The saved source file itself confirms `osm_type=relation` and `osm_id=2560355`; the identifier-based URL fixes the object independently of a text search.
- Nominatim `polygon_threshold` was not supplied; the documented default is `0.0`, and no post-download simplification was applied.
- Buffer: `0 m`, fixed a priori because the RoI represents the event area strictly.
- Licence: © OpenStreetMap contributors, Open Database License (ODbL) 1.0.
- Generated area: `0.905 km2`.

The original geometry is preserved as `osm_autodromo.geojson`. The validated output is `roi.geojson`.

## Analysis domain

The main analysis domain is independent of the event boundary. It is the bounding box of the 109 unique ANATEL cell-site coordinates, eroded by `R_max = 1000 m` in SIRGAS 2000 / UTM 23S (`EPSG:31983`). This is the conservative region where the site inventory is complete for candidate observers within `R_max`. Cell sites are never clipped; they remain candidates whenever they are within `R_max` of a sample.

The generated domain area is `4.685 km2`. It retains `90.86%` of the cleaned flight samples. The event RoI has `91.98%` of its area inside the analysis domain.

## ANATEL extract provenance

The input extract is `data/external/anatel/Estacoes_SMP_interlagos.csv`. It contains 1,124 station records. It was extracted from the Anatel open-data station records for Serviço Móvel Pessoal (SMP), restricted to `Município-UF == "São Paulo - SP"`; no flight-derived spatial filter was used. The extraction date is 2026-10-16. The official Anatel open-data policy describes these datasets as available under an open licence permitting reuse with attribution: https://www.gov.br/anatel/pt-br/dados/dados-abertos. The station-licensing context is documented at https://www.gov.br/anatel/pt-br/regulado/outorga/telefonia-movel/estacoes-radio-base.

Its `Município-UF` column contains only `São Paulo - SP`. The 1,124 records collapse to 109 unique sites by the exact pair (`Latitude decimal`, `Longitude decimal`), as required by the one-sniffer-per-site rule.

The domain computation uses all 1,124 records after coordinate parsing and deduplicates only for the site geometry. No operator, technology, frequency, or sector row is discarded before site deduplication. The source CSV SHA-256 at this freeze is `311c85de3c187ebd2a35c48c99484011dbec784b10bf1a8a761444e02338da8e`.

## Generated artifacts

- `osm_autodromo.geojson`: preserved source geometry and OSM relation metadata.
- `roi.geojson`: RoI after the declared 0 m buffer.
- `domain.geojson`: ANATEL-derived analysis domain.
- `roi_report.json`: areas, sample fractions, candidate-site counts, and SHA-256 hashes.
