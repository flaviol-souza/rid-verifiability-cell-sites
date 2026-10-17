# Stage A — cleaning rules v2 and deviation log (G0-v1 → v2)

Status: fixed on 16 Oct 2026, **before** the G0-v2 run. Thresholds are unchanged from v1.
Evidence: `results/g0_data/20261016T193702Z/` (G0-v1 run and `diag/`), audit findings N11–N12.

## Why v1 was revised

G0-v1 failed on its pre-set criterion: C9 excluded 514/13,966 = 3.55% > 1%. The read-only diagnostic found two
causes, both properties of the data that the v1 rules did not model. Neither cause is a GNSS error.

1. **Three positions per message (N11).** Each (serial, second) carries up to three rows, in a fixed file order.
   In the 14,341 complete groups: the 1st row is the highest in 96% of groups (AGL p50 26.8 m) and moves most → **drone**;
   the 2nd sits 4.7 m from the 3rd (median), AGL p50 5.9 m → **pilot/operator**; the 3rd is fixed within the session
   (100% at the modal point, median), AGL p50 6.5 m → **home (take-off point)**. In groups of two, the 1st row is above
   the 2nd in 99.3% of cases; groups of one have AGL p50 23.8 m (drone only). v1 kept the first row, which is the drone,
   but without stating why or keeping the other roles.
2. **Stepped position logging.** In 95% of consecutive steps the position does not change; it is held for ≈ 11 s
   (median) and then jumps. Dividing the jump by 1 s produces a fictitious speed. Measured from the time the previous
   position was first reported, C9 exclusions fall from 242 to 3 in the diagnostic run.
3. **Ground offset (N12).** Ground points (pilot, home) sit at ≈ +6 m above GLO-30 (session median; p10–p90 ≈ 4–9 m),
   so the v1 C8 threshold (AGL > 5 m) did not separate ground from flight.

## Rules v2

| # | v1 | v2 |
|---|----|----|
| C1 | Exact duplicates | Unchanged (keeps the first occurrence, so file order is preserved) |
| C2 | Keep the first row per (serial, timestamp) | **Role split by file order:** 1st = drone (kept in the track); 2nd = pilot (groups of 3) or ground reference (groups of 2); 3rd = home; ordinals ≥ 4 = unknown. Non-drone rows go to `data/interim/ground_refs.parquet` |
| C3 | Serials with no sample in the analysis domain | Serials with no sample in the **bounding box of the unique ANATEL sites** (samples near the domain are left to C8, so each removal is attributed to the right rule) |
| C4–C6 | — | Unchanged |
| C7 | AGL = alt − DEM | **Anchored AGL:** agl = alt − DEM − offset_session; offset = median(alt − DEM) over the session's home rows, else over its pilot/ground-reference rows, else 0 (`agl_anchor = none`). The unanchored value is kept as `agl_dem_m` |
| C8 | AGL > 5 m inside the domain | Unchanged threshold, applied to the anchored AGL |
| C9 | Speed = displacement / time since the previous retained sample | Speed = displacement / time since the previous retained position was **first reported**; repeated positions are never excluded. Threshold 40 m/s and the 1% G0 limit unchanged. The v1 count is reported as a diagnostic |

New G0 criterion (sanity of the role rule, declared here): in messages with a second position, the first position
is above the second (DEM-relative) in ≥ 90% of cases.

## Publication and privacy

- `flights_anon.csv` contains **drone positions only** (after C1–C2). Pilot and home positions are personal data
  (LGPD): they stay in `data/interim/` (git-ignored) and appear in the paper only as aggregates.
- The `flights_anon.csv` produced by the G0-v1 run contains all three roles and **must not be committed**.

## Sensitivity analyses (declared now)

- AGL: anchored (primary) vs DEM-only (`agl_dem_m`).
- Samples from groups of one (`group_size == 1`): included (primary) vs excluded.
- C9 estimator: v2 (primary) vs v1 (count only).
