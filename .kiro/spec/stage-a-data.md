# Spec input — `stage-a-data` (DS-v2)

> Paste this into Kiro when creating the spec "stage-a-data" (Feature Spec), so Kiro generates `requirements.md`, `design.md` and `tasks.md` from it.
> Source of truth: `research.md` (G0, BM-4/5/6/7/17/27), `methods.md` (Stage A, rules C1–C9, tests T1, T5, T12, T13), `structure.md` (rules 1–5).
> Out of scope: channel (Stage B), attacks (Stage C), detectors, `position_bucket.csv` (discontinued; never published).

## Goal

Turn the raw GP 2025 flight logs and the ANATEL extract into frozen, anonymized, physically plausible inputs for the simulator, and produce the G0 gate table.

## Requirements (EARS)

### R1 — Anonymization (BM-6)
User story: As the author, I want every drone identifier replaced by a keyed pseudonym, so that the published logs cannot be linked back to real serial numbers.
1. WHEN the anonymizer runs THE SYSTEM SHALL replace every value of `flight_id` (including literal values such as `encrypted`, and serials later excluded by cleaning) with `uas_` + the first 12 hex characters of HMAC-SHA256(key, serial).
2. WHEN the environment variable holding the key is missing THE SYSTEM SHALL stop with an error and write no output.
3. THE SYSTEM SHALL never write the key, or a raw serial, to any file under `data/external/` other than `data/external/flights/raw/` (git-ignored).
4. WHEN two different serials map to the same pseudonym THE SYSTEM SHALL stop with an error (collision check).
5. THE SYSTEM SHALL write `data/external/flights/flights_anon.csv` and a `flights_anon.sha256` file.
6. WHEN the leak test runs THE SYSTEM SHALL fail if any raw serial string occurs in any git-tracked file (test reads the serial list from `raw/`, never from a constant).

### R2 — Sites (Stage A)
1. THE SYSTEM SHALL collapse the 1,124 ANATEL station records into one row per unique (lat, lon) site, keeping operator and the list of collapsed record IDs.
2. WHEN the extract is loaded THE SYSTEM SHALL verify its SHA-256 against the value recorded in `data/external/anatel/README.md` and stop on mismatch.
3. THE SYSTEM SHALL write `data/interim/sites.parquet` (expected 109 sites: Operator I/II/III counts reported, operator names mapped to anonymized labels in outputs used by the paper).

### R3 — Cleaning C1–C9 (methods.md, Stage A)
1. THE SYSTEM SHALL apply C1 (exact duplicates), C2 (one sample per (serial, timestamp), rule from BM-17 default: keep first), C3 (serials outside the analysis domain extent, e.g. the São José dos Campos serial), C4 (placeholder serials, e.g. `MissionAlpha`), C5 (sentinel altitudes: MSL < 100 m), in this order.
2. WHEN a rule runs THE SYSTEM SHALL append (rule, rows_before, rows_dropped, rows_after, serials_affected) to `data/interim/cleaning_log.csv`.
3. THE SYSTEM SHALL sessionize (C6) with T_gap = 60 s read from `experiments/configs/reference.yaml`.
4. THE SYSTEM SHALL compute AGL (C7) only in `src/drs/data/agl.py`, as MSL altitude − GLO-30 elevation (EGM2008) sampled at the sample position, and SHALL drop the MSL column afterwards.
5. THE SYSTEM SHALL keep samples with AGL > 5 m inside `domain.geojson` (C8) and tag each with `in_roi` from `roi.geojson`.
6. WHEN the implied ground speed between consecutive samples of a session exceeds 40 m/s THE SYSTEM SHALL flag the later sample as `speed_outlier` and exclude it (C9), logging the count.
7. THE SYSTEM SHALL write `data/interim/samples.parquet` with columns: `sample_id, session_id, uas_id, t_utc, lat, lon, agl_m, in_roi`.

### R4 — Determinism and units
1. WHEN Stage A runs twice on the same inputs and config THE SYSTEM SHALL produce byte-identical `samples.parquet`, `sites.parquet` and `cleaning_log.csv` (T5 for Stage A).
2. THE SYSTEM SHALL compute every duration with `.dt.total_seconds()` (T12); a test with a known session SHALL return its known duration under pandas ≥ 2.

### R5 — G0 gate table
1. THE SYSTEM SHALL produce `results/g0_data/<timestamp>/g0_table.csv` and a provenance file with: cleaning log; number of serials and sessions; AGL p1/p5/p50/p95/p99; implied-speed p50/p95/p99 and outlier count; fraction of samples in the domain and in RoI ∩ domain; DEM missing count.
2. THE SYSTEM SHALL mark G0 as PASS only if: AGL p50 ∈ [10, 120] m; no retained AGL < −5 m (T1); speed outliers ≤ 1% of samples (above that: FAIL and investigate, never raise the bound after seeing data); 100% of retained samples inside the domain; DEM missing = 0.
3. WHEN G0 fails THE SYSTEM SHALL write the failing criteria and stop downstream stages.

## Acceptance tests to create (pytest)
T1 (AGL), T5-A (determinism), T12 (time units), T13 (physical sanity incl. speed), leak test (R1.6), collision test (R1.4), cleaning-log accounting (rows_after of rule k = rows_before of rule k+1).
