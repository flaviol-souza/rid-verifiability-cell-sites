---
inclusion: fileMatch
fileMatchPattern: ["src/**", "analysis/**", "experiments/**", "tests/**", "tools/**", "paper/**"]
---
# Remote ID observability from cellular infrastructure — Methods, Environment and Conventions

> **How** the work is done: environment, pipeline, metrics, protocol, statistics, conventions and what counts as "verified".
> Items marked ⚠ are fixed in the pilot and then frozen.

## Mandatory environment

| Layer | Technology | Details |
|-------|-----------|---------|
| Machine | Any host with Python; **Git only from WSL** on Windows (line endings, see `.gitattributes`) | Pure Python pipeline |
| Language | Python 3.11+ | numpy, scipy, pandas ≥ 2, pyarrow; versions locked |
| Geospatial | rasterio, shapely ≥ 2, pyproj | DEM, RoI and domain frozen with hashes |
| Orchestration | `experiments/run_stage_a.py` (Stage A), `experiments/run.py` (blocks), Make | Automatic provenance |
| Analysis | numpy, pandas, scipy, statsmodels | `analysis/` |
| Figures | matplotlib + `analysis/style.mplstyle` | Vector PDF, SBC column width, greyscale-readable |
| Writing | LaTeX, SBC template, **English** | latexmk, BibTeX |
| Assistant | Kiro (steering wrappers + specs) and Claude | Tests are the contract; plan before code |

**Not used:** detectors, attack generators, network emulation, legacy pipeline.

## Pipeline

Three stages. The simulator produces honest observations; the analysis computes observability, verifiability and characterization. **No stage reads pilot/home positions except Stage A (anchoring) and the characterization, which aggregates them.**

```
[ANATEL csv] ─► Stage A: data ─► sites.parquet, samples.parquet (drone track), ground_refs.parquet (private)
[flight logs] ─►  C1–C9 (v2)        cleaning_log.csv, g0_table.csv
[DEM, RoI, domain] ─►
                     │
                     ▼
                Stage B: channel ─► observations.parquet (sample × candidate site: rssi_dbm or "not heard")
                     │
──────────────────── simulator / analysis boundary
                     ▼
                Stage C: analysis ─► observability, verifiability (V3/V4), shadow windows, characterization
```

### Stage A — data (rules v2; implemented and tested)

Inputs in `data/external/` with source, licence, access date and hash: ANATEL extract (1,124 records → 109 sites), GP 2025 logs (raw, git-ignored), GLO-30 crop (EGM2008), RoI and domain.

| # | Rule (v2) |
|---|-----------|
| C1 | Drop exact duplicates (keeps first; file order preserved) |
| C2 | **Role split by file order:** 1st = drone (track), 2nd = pilot (groups of 3) / ground reference (groups of 2), 3rd = home; others to `ground_refs.parquet` |
| C3 | Drop serials with no sample inside the bounding box of the unique sites |
| C4 | Drop placeholders (one timestamp and one position) |
| C5 | Drop sentinel altitudes (alt < 100 m MSL) |
| C6 | Sessionize, T_gap = 60 s |
| C7 | **Anchored AGL** (only in `agl.py`): agl = alt − DEM − offset_session; offset from home rows, else pilot/ground refs, else none (flagged); `agl_dem_m` kept |
| C8 | Keep AGL > 5 m inside the analysis domain; tag `in_roi` |
| C9 | Exclude samples with implied speed > 40 m/s, speed = displacement / time since the previous retained position was **first reported** |

Deviation log and evidence: `docs/stage-a-rules-v2.md`. G0-v1 (FAIL, C9 = 3.55%) stays recorded in `results/g0_data/20261016T193702Z/`.

**Publication:** `flights_anon.csv` holds drone positions only (keyed pseudonyms `uas_` + 12 hex). Pilot and home positions never leave `data/interim/`.

### Stage B — channel (honest traffic only)

$$P_{rx,i}(t) = P_{EIRP} - PL_0 - 10\,\eta\log_{10}\frac{d_i(t)}{d_0} + X_i(t)$$

- $d_i$: 3D distance between the drone (anchored AGL) and receiver i at $h_{rx}$.
- $PL_0$: free-space loss at $d_0$ = 1 m, 2.4 GHz, plus a declared clutter term ⚠ (no source yet; part of the γ/R sweep).
- $X_i(t)$: AR(1) along path distance, $\rho = e^{-\Delta s/d_{corr}}$; $d_{corr}=0$ gives i.i.d. (⚠ BM-9).
- Candidate sites: all sites within R_max = 1 km of the sample (sites never clipped).
- Heard if $P_{rx,i} \ge \gamma$; unheard pairs recorded as unheard (T6).

| Family | Parameters | Source |
|--------|-----------|--------|
| C1 | η = 2.2, σ = 6 dB | Generic, declared assumption |
| C2 | Exponent, PL(d0), σ fitted on real Remote ID flights | GhostBuster (⚠ BM-1); used only inside its fitted range |

P_EIRP = 20 dBm (Holybro Remote ID datasheet, ERP used as EIRP, BM-25). γ = −95 dBm (⚠ BM-8), swept over 7 levels. Report the implied range $R = d_0\,10^{(P_{EIRP}-PL_0-\gamma)/(10\eta)}$ next to every result.

Determinism: same seed and inputs ⇒ byte-identical `observations.parquet` (T5); seeds derived per (block, cell, replica, session, site).

### Stage C — analysis

**Observability (RQ2).** Per sample: $|S|$. Per session: fraction of time with $|S| \ge k$, k ∈ {1, 2, 3, 4}, time-weighted by the interval to the next sample (capped at T_gap). Shadow windows: maximal intervals with $|S| < k$; duration (s) and distance flown (m); stratified by `in_roi`.

**Verifiability (RQ3).**
- **Fisher information of RSS with log-normal shadowing** (form as in Patwari et al. 2003, ⚠ Eq. 10 to be checked): for each receiver in S, $g_i = \frac{10\eta}{\sigma\ln 10}\,\frac{\mathbf{u}_i}{d_i}$, with $\mathbf{u}_i$ the horizontal unit vector from the receiver to the drone and $d_i$ the 3D distance (horizontal gradient of $10\eta\log_{10} d_i$ is $\frac{10\eta}{\ln 10}\frac{\Delta_{xy}}{d_i^2}$). $J = \sum_i g_i g_i^\top$; $\sigma_h = \sqrt{\mathrm{tr}(J^{-1})}$.
- **V4:** augment each row with $1/\sigma$ for the unknown power offset (3×3 J); $\sigma_h$ from the 2×2 position block of $J^{-1}$.
- **V3:** $|S| \ge 3$ and $\sigma_h \le D$; **V4:** $|S| \ge 4$ and $\sigma_h \le D$; D ∈ {50, 100, 200} m, reference 100 m. Singular J (collinear receivers) ⇒ not verifiable.
- HDOP (unweighted unit vectors) reported as a descriptor only.
- Reported as upper bounds on the coverage of any RSS multilateration check.

**Characterization (RQ1)**, from Stage A outputs only:
- rows per message and roles; AGL by role; drone–pilot and drone–home distance distributions (aggregates only);
- hold duration of positions (time between position changes) and its CDF;
- serial formats (counts only), `encrypted` share; serials seen on more than one day;
- sessions per serial, session durations, fraction in RoI.

## Conformance tests

| # | What | How |
|---|------|-----|
| T1 | AGL conversion and anchoring | Known DEM points; anchor priority; MSL column dropped |
| T2 | Geodesy | Known distances (horizontal and 3D) |
| T3 | Channel equation | RSSI at known distances = closed form, constants read from config |
| T4 | Shadowing statistics | Empirical σ and lag-d_corr autocorrelation ≈ e⁻¹ |
| T5 | Determinism | Byte-identical Stage A outputs and observations |
| T6 | Censoring recorded | Every (sample, candidate site) pair appears |
| T12 | Time units | `.dt.total_seconds()`; known durations |
| T13 | Physical sanity | Shadow window ≤ session duration; distances within the domain scale; speeds ≤ G0 bound |
| T15 | CRLB and HDOP | Known geometries: square of 4 receivers gives the closed-form σ_h; collinear receivers give a singular J (not verifiable); σ_h scales linearly with σ and with distance |
| T16 | Role split | File-order roles; role consistency computed |
| T17 | Privacy | Published file has drone rows only; leak test over tracked files; pilot/home never in `results/` figures except aggregates |

Rule: a test that checks a parameter reads it from config, never from a repeated constant.

## Experimental protocol

| ID | Goal |
|----|------|
| `g0_data` | G0 (v2) |
| `g2_channel` | C1/C2 with sources; implied range table |
| `blockC_char` | RQ1 tables and figures |
| `blockO_obs` | RQ2, H1 |
| `blockV_verif` | RQ3, H2 (same observations as O) |
| `blockS_sens` | H3 and robustness |

Order: G0 → G2 → O → V → S; C can run right after G0. Pilot with small N to measure cost; the pilot does not enter the paper.

## Statistical analysis (defined before seeing the data)

| Situation | Test |
|-----------|------|
| H1 — shadow fraction, consortium vs best single operator | Paired Wilcoxon signed-rank by session; Holm over the R grid; effect size with 95% cluster-bootstrap CI (serials) |
| H2 — verifiability gap | Mean gap per session with 95% cluster-bootstrap CI; criterion: lower bound > 0.10 at reference (confirmed 17 Oct 2026) |
| H3 — ranking robustness | Paired differences per (family, γ) with CIs; flips reported as boundaries |
| RQ1 | Descriptive (counts, medians, quantiles); no tests |

Rules: α = 0.05; effect sizes and 95% CIs always; statistical unit = serial for the bootstrap, session for exposure; seeds averaged within each session; per-serial weights shown; exploratory analyses labelled.

## Construction references

> ✔ = checked · ⚠ = from memory or secondary source; resolve before citing.

| Reference | Use | Status |
|-----------|-----|--------|
| ASTM F3411 | Message content | ⚠ edition |
| RFC 9153, RFC 9374, RFC 9434, RFC 9575 | DRIP; RFC 9575 §3.1.2.2 and §9.1 quote | ✔ |
| draft-moskowitz-drip-crowd-sourced-rid | Crowd-sourced receivers | ⚠ latest version |
| Keizer, Sciancalepore, Oligeri, "GhostBuster", IEEE CCNC 2024 | RSS verification; channel family C2 | ⚠ resolve DOI (BM-24) |
| Høffer et al., IMAV 2024 | RSSI localization with a receiver mesh | ✔ |
| Strohmeier, Lenders, Martinovic, ACM CPSS 2015 | Location verification analogue | ✔ |
| Li et al., Drones 5(3):76, 2021 | Remote ID at large public events | ⚠ |
| Gudmundson, Electronics Letters, 1991 | Correlated shadowing | ⚠ details |
| Holybro Remote ID datasheet | P_EIRP | ✔ |
| Receiver datasheet | γ | ⚠ BM-8 |
| N. Patwari, A. O. Hero III, M. Perkins, N. S. Correal, R. J. O'Dea, "Relative Location Estimation in Wireless Sensor Networks", IEEE Trans. Signal Processing 51(8):2137–2148, 2003 | RSS Fisher information / CRLB (V3/V4) | ✔ metadata · ⚠ Eq. 10 |
| Penn State GEOG 862, "The Space Segment: Dilution of Precision" | GNSS practice (PDOP mask ≈ 6), cited only to explain why HDOP is not used as threshold | ✔ |
| Milbert (Langley column), "Innovation: Improving Dilution of Precision", GPS World, Nov 2009 | DOP as random-error propagation | ✔ |
| Efron, Tibshirani, 1993 | Cluster bootstrap | ⚠ |

Reading notes in `literature/notes/{key}.md`; no numeric value enters a config from a paper if a datasheet or standard gives it.

## Writing conventions

- SBC template unchanged; 14 pages including references.
- Abstract: question + data + main numbers (observable fraction, V3/V4 fractions, consortium gain) + implication.
- Numbered contributions, each verifiable in the results.
- Fixed terminology: "drone", "cell site", "receiver", "observer set", "observable", "verifiable (V3/V4)", "structural shadow", "consortium". Defined at first use.
- Explicit labels for **measured** (trajectories, sites), **modelled** (reception), **assumed** (h_rx, clutter term).
- Every number via macro from `analysis/`; missing results as visible `\TODO{}`.

## Verification checklist per experiment

1. ☐ `provenance.yaml` with commit not `-dirty`.
2. ☐ G0 (v2) and G2 passed on the same code version.
3. ☐ Conformance tests green.
4. ☐ Seeds executed as planned; discards listed with reasons.
5. ☐ `make analysis` regenerates every figure and table.
6. ☐ Physical sanity checked.
7. ☐ No pilot/home position in any figure or table except aggregates.

## Integrity and ethics

- The rejected SBRC 2026 submission is not cited or described.
- Pilot and home positions are personal data: never published, aggregates only.
- Third-party data with source and licence; serials pseudonymized with a keyed hash (key never stored).
- No over-the-air transmission; no spoofing performed.
- AI use declared per SBC policy; text and references checked by the authors.

## Artifact

⚠ Check SBRC 2027 CTA badges. README with contents, requirements and time per block; minimal test ≤ 10 min (G0 on synthetic data + reduced block O); figure/table → command map; DOI equal to the submitted tag.
