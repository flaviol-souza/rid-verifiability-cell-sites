---
inclusion: always
---
# Remote ID observability from cellular infrastructure — Research Summary (SBRC 2027)

> **What** is being studied, **why**, with **which concepts**, and what is still owed.
> Items marked **⚠ VERIFY** depend on a source not yet checked. Do not remove them without checking.
> Scope decided on 16 Oct 2026: proposal **C** (observability of the cellular grid) with the data characterization as a section and the **verifiability upper bound** inside. No detectors, no attacks, no A3P.
> The previous plan (spoof-or-vanish, detectors D0–D4) is archived in `claude/ds-sbrc2027/archive/research-dsv2-spoof-or-vanish.md`.

## What it is

**A measurement-driven study, on real drone trajectories from a mass event and the real topology of three mobile operators, of how much of the flight time passive 2.4 GHz receivers co-located at existing cell sites could observe through Remote ID, and of where that observation is sufficient for any RSS-based check of the reported position.**

Working title: *How much of the sky can the cellular grid hear? Remote ID observability and verifiability at a mass event.* ⚠ (title to settle with the advisors)

Inputs that are **measured**: drone trajectories (2025 São Paulo Grand Prix, Interlagos; detection-system logs) and cell-site positions (ANATEL). Input that is **modelled**: reception (log-distance channel, two literature-anchored families, swept). Nothing here is a field measurement of Remote ID reception at a cell site.

**Central claim (falsifiable):**

> *On a dense urban topology, the existing cellular grid could hear most of the flight time of the drones at a mass event, but the time in which the received signals are sufficient to check the reported position (≥ 3 observers with usable geometry, ≥ 4 if the transmit power is unknown) is markedly smaller, depends on operator cooperation, and has a measurable spatial and temporal structure.*

If the gap turns out small (verifiability ≈ observability everywhere), that is reported: the grid would then be a credible verification substrate, which is also a result.

| Field | Value |
|-------|-------|
| **Type of work** | Conference paper + artifact |
| **Target venue** | SBRC 2027, main track — 14 pages in the SBC template, including references; **English** |
| **Deadlines** | Abstract **11 Jan 2027** · Full paper **18 Jan 2027** · Notification **15 Mar 2027** · Camera-ready **26 Mar 2027** (SBRC 2027 CFP, checked 15 Oct 2026; re-check in December) |
| **Review** | ≥ 3 reviewers; not double-blind (2027 CFP silent; 2026 submission carried names). Re-check the JEMS form. |
| **Artifact** | repository `cs-rid-spoofing` (⚠ rename to be decided) · DOI pending · CTA evaluation optional |
| **Relation to the thesis** | Related publication (not a thesis chapter). Reuses the GP 2025 data and pipeline started for Digital Shadows. |

### What carries over from Digital Shadows, and what does not

| Carries over | Does not |
|---|---|
| GP 2025 trajectories, ANATEL sites, GLO-30, RoI/domain (frozen with hashes) | The spoofing-detection question and its detectors (D0–D4) |
| Stage A v2 (role split, anchored AGL, C9 estimator) | Attackers A0–A5, spoof-or-vanish experiments (discussion only) |
| Channel families C1/C2 and the γ sweep | Legacy freeze (G1) and the legacy ablation (block L) |
| Audit findings as **data-quality lessons** (N1, N3, N11, N12) | Any citation or description of the rejected SBRC 2026 submission |

> **Rule on the rejected submission:** unpublished; never cited or described as "our previous work".

### Positioning (to verify in the literature pass)

RSS-based Remote ID verification exists (GhostBuster; Høffer et al., IMAV 2024) and the IETF CS-RID draft proposes crowd-sourced receivers. Those works evaluate **detectors** with receivers placed at will (random or dedicated). This paper asks the prior, infrastructure question that they leave open: **with the receivers a country already has (cell sites), how much of real drone traffic could be observed and verified at all?** It contributes the denominator that any detection rate implicitly assumes.

## Research questions

| ID | Question |
|----|----------|
| **RQ1 — Data** | What do drone identification broadcasts logged at a mass event actually contain, and which properties of the logs matter for any verification study (roles per message, protocol mix, update staleness, identifier persistence, operator exposure)? |
| **RQ2 — Observability** | What fraction of flight time is heard by at least k cell-site receivers, per operator and for the multi-operator deployment, as a function of the effective range? Where and for how long are the structural shadows? |
| **RQ3 — Verifiability bound** | What fraction of flight time satisfies the minimum condition for any RSS-based position check (|S| ≥ 3 with known transmit power, |S| ≥ 4 with unknown power, and geometry better than a dilution threshold)? How much smaller is it than observability, and how does it depend on operator cooperation and range? |

### Validations (entry gates)

| ID | What it validates | Pass criterion |
|----|-------------------|----------------|
| **G0** | **Data sanity** (Stage A v2; G0-v1 failed and is recorded; **G0-v2 PASS on 16 Oct 2026**, run `20261016T213222Z`, deterministic replica `…213229Z`) | AGL p50 ∈ [10, 120] m; no retained AGL < −5 m; C9 exclusions ≤ 1%; 100% of samples in the domain; DEM missing = 0; role consistency ≥ 0.90 |
| **G2** | **Channel anchoring** | Families C1 (generic, η = 2.2, σ = 6 dB) and C2 (GhostBuster-fitted, ⚠ BM-1) with sources; P_EIRP from datasheet; γ anchored and swept (⚠ BM-8). Every result reported as a function of the implied range R. |

### Hypotheses (fixed before running)

| ID | Hypothesis | Metric | Criterion for rejecting H₀ |
|----|------------|--------|-----------------------------|
| **H1** | **Cooperation reduces structural shadows.** The consortium has a smaller fraction of flight time with \|S\| < k than the best single operator. | Shadow-time fraction per session, k ∈ {1, 3} | Paired Wilcoxon signed-rank by session, α = 0.05, Holm over the R grid; effect size with 95% CI (cluster bootstrap by serial) |
| **H2** | **Verifiability gap.** The fraction of flight time that is verifiable (V3: \|S\| ≥ 3 and Cramér–Rao horizontal error σ_h ≤ D = 100 m) is smaller than the observable fraction (\|S\| ≥ 1) by a non-trivial margin at the reference range. | Gap = observable − verifiable, per session | 95% cluster-bootstrap CI of the mean gap entirely above **0.10** (minimum effect, confirmed by the lead author on 17 Oct 2026) at reference; reported across the R grid |
| **H3** | **Robustness of the ranking.** The ordering consortium > each single operator (for V3) holds under both channel families and across the γ sweep. | Sign of the paired difference per (family, γ) | Same sign with CI excluding 0 in every (family, γ) cell, or the cells where it flips are reported as the boundary |

> RQ1 is descriptive (no hypothesis test); its numbers come from the Stage A outputs.
> Any analysis decided after seeing the data is labelled **exploratory**.

### Preliminary facts (exploratory, from the v26 data and the G0-v1 diagnostic; regenerate with the pipeline)

- 61,497 rows, 24 serials, 4–9 Nov 2025; most rows on 8–9 Nov (race weekend).
- Up to three positions per message, in fixed file order: drone, pilot/operator, home. 14,341 complete triples; drone–pilot distance median 164 m, max 821 m.
- Serial formats: 15 of 16 characters starting with a letter, 6 of 14 starting with a digit, one literal `encrypted` → likely a mix of standard Remote ID and DJI DroneID (⚠ BM-28).
- Logged at 1 Hz, but the position changes every ≈ 11 s (median; p90 39 s).
- 5 of 24 serials appear on more than one day.
- AGL from GLO-30: drone p50 ≈ 27 m (DEM-only); ground points sit ≈ +6 m above the DEM (anchoring in Stage A v2).

## Contributions

1. **Characterization of drone identification broadcasts at a mass event** (RQ1): what the logs contain and the pitfalls they set for verification studies (three positions per message, stepped updates, protocol mix, identifier persistence, operator exposure in aggregate).
2. **Observability of the existing cellular grid** (RQ2): fraction of flight time and shadow structure per operator and for the consortium, on real trajectories with terrain-anchored altitude, under two channel families and a range sweep.
3. **An upper bound on RSS-based position verifiability** (RQ3): where any RSS multilateration check (GhostBuster-style) can work at all on this infrastructure, with known and unknown transmit power.
4. **Open artifact**: Stage A pipeline with tests, anonymized drone tracks (drone positions only), and a scenario format (site list + trajectories) that transfers to other events and cities.

**Out of scope (declared):** detectors and their accuracy; attackers (the spoof-or-vanish argument appears only in the discussion); field measurement of reception; cryptographic validity of messages (DRIP assumed); timing-based verification; A3P and airspace dissemination; publication of pilot or home positions.

## Roadmap (only to bound this paper)

| | This paper (SBRC 2027) | Possible follow-up |
|---|---|---|
| Question | How much can the grid observe and verify? | Do detectors reach the bound under an adaptive attacker (spoof-or-vanish), and does it hold on measured RSSI? |
| Needs | Existing data | RSSI from the detection system (⚠ BM-28) or a measurement campaign |

## Roles

| Role | Person | Responsibility |
|------|--------|----------------|
| Lead author | Flavio L. S. Souza | Design, implementation, writing |
| Advisor | Carlos H. C. Ribeiro (ITA) | Method and positioning |
| Co-advisor | Lourenço Alves Pereira Junior (ITA) | Method and positioning |
| Co-advisor | Andrei Gurtov (LiU) | DRIP/IETF context |
| Co-authors | André L. E. Melo, Antonia M. A. da Silva (2026 version) | ⚠ confirm and record contributions (BM-26) |

## Domain concepts

### Scenarios
Same code; only the site list changes.

| Scenario | Sites | Role |
|----------|-------|------|
| `interlagos_op1` / `op2` / `op3` | Sites of one operator (30 / 23 / 56 in the extract) | Single-operator deployments |
| `interlagos_consortium` | All 109 sites (no shared sites) | **Main scenario** |

Operators appear anonymized (Operator I, II, III).

> **RoI, analysis domain and sites are different things.** The RoI (Autódromo, OSM relation 2560355, 0 m) is the event zone and a reporting stratum. The analysis domain (site bounding box eroded by R_max = 1 km) selects the samples of the primary statistics, because only there is the candidate-site set complete. Sites are never clipped.

### Cell site and receiver
A cell site is a unique (lat, lon) in the ANATEL extract; station records at the same site are collapsed. **One receiver per site**, at height h_rx (⚠ BM-3, assumption 30 m AGL).

### Message roles (Stage A v2)
Each (serial, second) carries up to three rows in fixed order: 1st = **drone**, 2nd = **pilot/operator** (generic ground reference in groups of two), 3rd = **home**. Only the drone track enters the observability analysis; pilot/home positions anchor the AGL and feed the characterization **in aggregate only**.

### Serial and session
A session is a maximal run of a serial with no gap > T_gap = 60 s. The **serial** is the cluster for the bootstrap; the **session** is the unit of exposure for time fractions.

### Channel and observer set
$P_{rx,i} = P_{EIRP} - PL_0 - 10\,\eta\,\log_{10}(d_i/d_0) + X_i$, with $d_i$ the 3D distance from the drone (anchored AGL) to receiver i, and $X_i$ log-normal shadowing, AR(1) along the path (⚠ d_corr, BM-9). Receiver i **hears** if $P_{rx,i} \ge \gamma$. Observer set $S(t)$, redundancy $|S(t)|$.

### Observability, verifiability, shadows
- **Observable at level k:** $|S| \ge k$.
- **Verifiable (V3):** $|S| \ge 3$ and $\sigma_h \le D$, where $\sigma_h$ is the Cramér–Rao lower bound on the horizontal position error from the RSS of the observer set (known transmit power, altitude taken from the message). **V4:** $|S| \ge 4$ with the transmit power as an extra unknown, and $\sigma_h \le D$. D ∈ {50, 100, 200} m, reference 100 m (decided 17 Oct 2026): no check can tell a false position from the true one when the localization uncertainty exceeds the displacement in question. These are **necessary** conditions for any RSS multilateration check, hence an **upper bound** on what a detector can cover. HDOP is reported only as a geometry descriptor (in RSS the range error grows with distance, so HDOP alone does not measure precision).
- **Structural shadow window:** maximal interval of a session with $|S| < k$; reported with duration and distance flown, inside and outside the RoI.

### Notation

| Symbol | Meaning | Unit | In code |
|--------|---------|------|---------|
| $\gamma$ | receiver sensitivity | dBm | `sniffer_sens_dbm` |
| $P_{EIRP}$ | nominal transmit power | dBm | `eirp_dbm` |
| $\eta$, $\sigma$, $d_{corr}$ | exponent, shadowing σ, decorrelation distance | —, dB, m | `eta`, `shadow_sigma_db`, `shadow_dcorr_m` |
| $h_{rx}$ | receiver height | m | `sniffer_height_m` |
| $R$ | implied range | m | `range_m` |
| $S$, $\lvert S\rvert$ | observer set, redundancy | — | `observers`, `n_obs` |
| $k$ | observability level | — | `k_min` |
| $\sigma_h$ | Cramér–Rao bound on horizontal error | m | `crlb_h_m` |
| $D$ | verifiability scale (50/100/200 m; ref. 100 m) | m | `verif_scale_m` |
| $T_{gap}$ | session gap | s | `session_gap_s` |

## Experimental design

One simulator (honest traffic only), one run matrix, analysis-side metrics. Reference configuration: consortium; all retained sessions (G0); AGL anchored (Stage A v2); channel C1 (η = 2.2, σ = 6 dB); d_corr ⚠ BM-9; γ = −95 dBm (⚠ BM-8); P_EIRP = 20 dBm; h_rx = 30 m; k ∈ {1, 2, 3, 4}; D = 100 m (levels 50/100/200 m).

| Block | Crossed factors | Cells | Seeds |
|-------|-----------------|-------|-------|
| **C — Characterization** | none (descriptive, from Stage A outputs) | — | — |
| **O — Observability** | Channel family (2) × γ (7 levels) × Scenario (4) | 56 | 20 |
| **V — Verifiability** | Same as O × D (3 levels: 50/100/200 m), computed on the same observations | 168 (analysis-side) | 20 |
| **S — Sensitivity** | σ (4/8 dB), d_corr (i.i.d./long), h_rx (15/45 m), AGL (anchored/DEM-only), T_gap (30/300 s), group-size-1 samples (in/out), unanchored sessions (in/out; 12 of 89 in G0-v2), each at 2 levels | 14 | 10 |

V reuses O's observations (no new simulation). Expected cost: minutes to hours on a laptop (⚠ BM-21).

## Empirical motivation

1. **Authentication is not truth.** RFC 9575 §3.1.2.2: *"Whether the content is true is a separate question that DRIP cannot address"*; §9.1 suggests checking location against observations. Any such check needs observers; this paper measures how many the existing grid provides.
2. **The scenario is real.** Trajectories logged during the 2025 São Paulo Grand Prix by a drone-detection system (⚠ provenance and permission, BM-6), and the licensed sites of three operators.
3. **The data itself teaches something.** The logs mix drone, pilot and home positions in the same rows; a study that ignores this measures the ground, not the air (audit N11).

## Positioning (related work)

| Line | Key references | Gap this paper addresses |
|------|----------------|--------------------------|
| Remote ID and DRIP | ASTM F3411 (⚠ edition); RFC 9153, 9374, 9434, 9575 | Authenticity, not truthfulness; no infrastructure for checking |
| RSS-based Remote ID verification | Keizer, Sciancalepore, Oligeri, "GhostBuster", IEEE CCNC 2024 (DOI 10.1109/CCNC51664.2024.10454860, ⚠ resolve); Høffer et al., IMAV 2024 | Receivers placed at will; no denominator from real infrastructure |
| Crowd-sourced Remote ID | draft-moskowitz-drip-crowd-sourced-rid (⚠ latest version) | Architecture, no evaluation on real traffic or topology |
| Location verification in aviation surveillance | Strohmeier, Lenders, Martinovic, ACM CPSS 2015 | ADS-B; receiver coverage taken as given |
| Remote ID at events / airspace management | Li et al., "UAS Remote Identification and Dynamic Airspace Management for Large Public Events", Drones 5(3):76, 2021 (⚠ verify) | No observability analysis on licensed infrastructure |
| Drone identification measurement | ⚠ search: DJI DroneID studies; Remote ID in-the-wild measurements | To be filled from the literature pass; do not cite from memory |

## Methodological backlog

| # | Description | Priority | Type |
|---|-------------|----------|------|
| BM-1 | **Transcribed 17 Oct 2026** from the authors' PDF (Sect. V-B Eq. 1; Table III): per-UA exponent 1.35 / 0.9 / 0.84 and PL(d0) 58.07 / 70.82 / 69.88 dB at d0 = 1 m; σ of the fit not stated (simulations use 3.5 dB; real-data results at σ ≈ 4.5 dB, Sect. VI-C); noise floor ≈ −95 dBm (Sect. VI-A); transmit power and fitted distance range **not stated**. Consequence: exponents < 2 cannot be extrapolated (at 20 dBm they imply ranges of tens of km), so C2 **cannot anchor R**; at most a sensitivity check of the curve shape. ⚠ Confirm by reading Table III yourself | Resolved (negative) | HITL check |
| **BM-31** | **Anchor for the implied range R.** No primary measurement of Broadcast Remote ID reception range found yet (Høffer et al., IMAV 2024, only cite "a few hundred meters" from a reference; their 1.6 km is a relay chain). Proposal: sweep R directly (100/200/300/500/750/1000 m) instead of γ, keep C1 shape (η = 2.2, σ = 6 dB), and report every result vs R | **High — blocks G2** | HITL decision |
| **BM-32** | **Inventory truncation.** With r_max = 1 km and σ = 6 dB, P(heard at 1 km) ≤ 1% only for R ≤ ≈ 232 m; larger R makes observability a lower bound. Options: extend the ANATEL extract (r_max 3 km → R ≤ ≈ 700 m; 5 km → ≈ 1.16 km) or restrict the R sweep. Also document how the extract was queried (BM-7 follow-up) | **High — blocks G2** | HITL decision |
| BM-2 | DEM — **resolved** (GLO-30, hashes frozen; DSM limitation declared) | Resolved | — |
| BM-3 | h_rx = 30 m AGL (assumption); S-block 15/45 m | Default | — |
| BM-4 | T_gap = 60 s — **resolved**; recount sessions after G0-v2 | Resolved | — |
| BM-5 | MissionAlpha excluded — **resolved** (rule C4) | Resolved | — |
| BM-6 | Flight-log provenance and permission; **confirm that publishing drone-only tracks is covered** and that pilot/home positions stay private | **High** | HITL |
| BM-7 | RoI/domain — **resolved**; follow-ups: exact Nominatim URL; how the ANATEL extract was queried | Low | HITL |
| BM-8 | γ source (receiver datasheet) to replace or bracket −95 dBm | High | HITL |
| BM-9 | d_corr source for elevated 2.4 GHz links (affects shadow-window durations) | Medium | HITL |
| BM-12 | Verify every ⚠ reference; reading notes | High | HITL |
| BM-13 | Abstract consistency | Near deadline | — |
| BM-14 | Page budget | Near deadline | — |
| BM-16 | Coverage shapefiles not used (5G cellular, unrelated to 2.4 GHz) | Default | — |
| BM-17 | No interpolation; stepped updates declared (and characterized in RQ1) | Default | — |
| BM-21 | Run budget measured in the pilot | Medium | HITL |
| BM-22 | Physical sanity of derived durations and distances | High | — |
| BM-24 | GhostBuster venue/DOI resolved before citing | High | HITL |
| BM-25 | ERP used as EIRP (conservative by 2.15 dB); inside the γ sweep | Default | — |
| BM-26 | Co-authors and CRediT | Medium | HITL |
| BM-27 | Vertical reference of `alt`; mitigated by home-anchored AGL; report anchored vs DEM-only | Medium | HITL |
| **BM-28** | **Ask the data provider:** protocol per detection (DroneID vs standard Remote ID); raw receptions or 1-Hz resampled; RSSI and sensor position available?; field dictionary; meaning of the three positions (confirms N11) | **High** | HITL |
| **BM-29** | **Resolved (17 Oct 2026):** HDOP threshold replaced by the Cramér–Rao horizontal error σ_h ≤ D, D ∈ {50, 100, 200} m (ref. 100 m). No citable HDOP threshold exists for RSS (the common GNSS rating table is unsourced; GNSS practice uses a PDOP mask ≈ 6, Penn State GEOG 862). Fisher information as in Patwari et al., IEEE TSP 51(8):2137–2148, 2003 (⚠ check Eq. 10 against the PDF before citing) | Resolved | — |
| **BM-30** | **Characterization ethics:** pilot/home positions reported only as aggregates (distances, counts); no maps of pilot locations | High | — |

## Threats to validity

| Type | Threat | Mitigation |
|------|--------|------------|
| Construct | Reception is modelled, not measured | Two literature-anchored families; γ sweep; results as functions of R; measured RSSI as follow-up (BM-28) |
| Construct | V3/V4 are necessary, not sufficient, for verification | Stated as an upper bound; no detector claim |
| Internal | Altitude reference error | Home-anchored AGL; DEM-only as sensitivity |
| Internal | Role assignment by file order | Role-consistency criterion in G0; confirmation from the provider (BM-28) |
| Internal | One serial dominating | Serial as bootstrap cluster; per-serial weights shown |
| External | One event, one city | Declared; scenario format transfers |
| External | Receivers assumed at every site | Declared; single-operator scenarios bracket sparser deployments |
| External | Stepped position updates | Characterized (RQ1); declared |
| External | DSM terrain | Declared; anchoring reduces the bias |
| Ethics | Pilot location is personal data | Never published; aggregates only (BM-30) |
| Statistical | Few serials (~20) | Cluster bootstrap; effect sizes with CIs; Holm |

## Claim → evidence matrix

| Claim | Evidence | Generated by | Status |
|-------|----------|--------------|--------|
| "The cleaned data is physically plausible" | Table G0 (v2) + deviation log v1 → v2 | `make_tables.py::table_g0` | ☐ |
| "The logs mix drone, pilot and home positions" (RQ1) | Table of roles, distances, AGL by role | `make_tables.py::table_roles` | ☐ |
| "Positions update in steps of ≈ 11 s" (RQ1) | CDF of hold durations | `make_figures.py::fig_hold` | ☐ |
| "The grid hears most of the flight time" (RQ2) | Observable fraction vs R per scenario | `make_figures.py::fig_observability` | ☐ |
| "Cooperation reduces structural shadows" (H1) | Paired shadow fractions, consortium vs best operator | `make_figures.py::fig_shadows_paired` | ☐ |
| "Verifiable time is markedly smaller" (H2, RQ3) | Observable vs V3/V4 vs R, per scenario (**main figure**) | `make_figures.py::fig_verifiability_gap` | ☐ |
| "Shadows have structure" (RQ2) | Shadow-window durations; map of shadow density (drone positions only) | `make_figures.py::fig_shadow_windows`, `fig_shadow_map` | ☐ |
| "Conclusions hold across parameters" (H3) | Sensitivity table/tornado | `make_figures.py::fig_sensitivity` | ☐ |

## Future work (already assumed)

- Detectors against the bound: does a GhostBuster-style detector reach V3/V4 coverage on this infrastructure, and what does a power-controlling spoofer gain (spoof-or-vanish)?
- Measured RSSI (from the detection system, if available, or a campaign) to anchor the channel.
- Verifiability of DRIP-authenticated evidence using the same observer sets.
