# Remote ID observability from cellular infrastructure — Repository Structure and Golden Rules

> **Where** each thing lives, and the rules that keep paper, code, data and literature consistent.

## Directory structure

```
cs-rid-spoofing/
├── research.md · methods.md · structure.md   # Single source of truth (Kiro steering pulls them by reference)
├── AGENTS.md · CLAUDE.md · README.md
├── .gitattributes                             # LF for text; data/** -text; *.parquet, *.tif binary
│
├── src/drs/                                   # SIMULATOR (stages A–B). Never imports analysis/.
│   ├── data/                                  # STAGE A (implemented, rules v2)
│   │   ├── anonymize.py                       # Keyed pseudonyms; key only from DSV2_HMAC_KEY
│   │   ├── clean.py                           # C1–C6, C8, C9 + cleaning log; C2 role split
│   │   ├── agl.py                             # C7: the ONLY place altitude is converted (anchored AGL)
│   │   ├── sites.py                           # ANATEL records → one row per site
│   │   └── stage_a.py                         # Orchestration + G0
│   ├── geo.py
│   └── channel/                               # STAGE B
│       ├── pathloss.py                        # Log-distance mean; constants from config
│       ├── shadowing.py                       # AR(1) along path; d_corr = 0 → i.i.d.
│       └── observe.py                         # Drone position → heard/unheard per (sample, candidate site)
├── analysis/                                  # STAGE C
│   ├── observability.py                       # |S|, time fractions, shadow windows
│   ├── verifiability.py                       # CRLB σ_h, V3/V4 (HDOP as descriptor)
│   ├── characterization.py                    # RQ1 aggregates (roles, holds, formats, days)
│   ├── stats.py                               # Cluster bootstrap, Wilcoxon, Holm, CIs
│   ├── make_figures.py · make_tables.py · style.mplstyle
│   └── notebooks/                             # Exploration only
├── tests/                                     # Contract: Stage A tests (done) + T1–T6, T12, T13, T15–T17
├── experiments/
│   ├── configs/
│   │   ├── reference.yaml                     # Stage A v2 + reference configuration
│   │   ├── scenarios/ (op1, op2, op3, consortium)
│   │   ├── channel/ (c1_generic.yaml, c2_ghostbuster.yaml — every constant with its source)
│   │   └── blockO_obs.yaml · blockV_verif.yaml · blockS_sens.yaml · blockC_char.yaml
│   ├── run_stage_a.py                         # Stage A + G0 (run by Flavio, key via read -rs)
│   └── run.py                                 # Blocks
├── data/
│   ├── external/                              # Third-party inputs with source, licence, date, hash
│   │   ├── anatel/ · terrain/ · roi/ · channel/
│   │   └── flights/
│   │       ├── raw/                           # GIT-IGNORED: real serials, all roles
│   │       └── flights_anon.csv (+ .sha256)   # PUBLISHED: drone positions only
│   ├── interim/                               # GIT-IGNORED: samples, sites, ground_refs (private), cleaning_log
│   └── raw/                                   # IMMUTABLE simulator outputs: observations.parquet
├── docs/
│   ├── audit-v26.md                           # Without raw serials
│   ├── stage-a-rules-v2.md                    # Deviation log G0-v1 → v2
│   └── adr/
├── literature/ (README, queries.yaml, notes/, exports/)
├── results/{exp_id}/{timestamp}/              # Config, commit, input/output hashes, logs, metrics
├── paper/ (main.tex, sections/, figures/ GENERATED, tables/ GENERATED, macros/results.tex GENERATED, refs.bib)
└── tools/ (freeze_dem.sh, check_terrain.py, make_roi.py)   # One-off, outputs frozen with hashes
```

`legacy/`, `src/drs/attacks/` and `analysis/detectors/` are **out of this paper**. Do not create them.

## Golden rules

1. **Configs are the single source of truth.** No hardcoded η, σ, γ, P_EIRP, clutter term, h_rx, D or threshold. Every channel constant enters with its source. Configs are copied to `results/` at the start of each run.
2. **`reference.yaml` defines what is not crossed.** Blocks inherit it and override only their crossed factors.
3. **No number typed by hand in the paper.** Macros, `make_figures.py`, `make_tables.py`; missing results as `\TODO{}`.
4. **`data/raw/` is immutable.** Filtering is code in `analysis/`.
5. **Altitude is converted in exactly one place** (`agl.py`). `alt` is dropped after conversion.
6. **Privacy by construction.** Raw serials only in `data/external/flights/raw/`; pilot/home positions only in `data/interim/`; both git-ignored. Published tracks are drone-only. Figures never show pilot or home locations; characterization reports aggregates. The leak test scans every tracked file.
7. **One Git.** On Windows, use only the Git of WSL; `.gitattributes` protects `data/` from line-ending conversion; never `--renormalize` data.
8. **Gates before results.** G0 (v2) and G2 pass on the same commit as any reported result; a `-dirty` run is exploratory.
9. **Names and units end to end.** One glossary (`research.md`); units in column names (`_m`, `_s`, `_db`, `_dbm`); scenario labels in one dictionary.

### Separation of responsibilities

| Layer | Does | Does not |
|-------|------|----------|
| `src/drs/data/` | Clean, split roles, sessionize, anchor AGL, filter domain | Simulate radio; analyse |
| `src/drs/channel/` | Heard/unheard observations from the drone track | Read pilot/home positions |
| `analysis/` | Observability, verifiability, characterization, statistics | Re-simulate; publish private positions |
| `experiments/` | Orchestration, seeds, provenance, gates | Contain logic |
| `paper/` | Argument | Hold a number not generated by `analysis/` |

## Paper section map (14 pages incl. references)

| Section | Budget | Answers |
|---------|--------|---------|
| Abstract | CFP limit | Question, data, observable vs verifiable fractions, consortium gain |
| Introduction | ~1.25 p. | Authentic ≠ true; checks need observers; how many does the grid give? contributions |
| Background and related work | ~1.5 p. | Remote ID/DRIP; RSS verification (GhostBuster, IMAV 2024, CS-RID); what they assume about receivers |
| Data and its pitfalls (RQ1) | ~2 p. | GP 2025 logs, roles per message, stepped updates, protocol mix, cleaning (G0 v2) |
| Method | ~1.5 p. | Sites and scenarios; channel families and sweep; observability; V3/V4 (Cramér–Rao bound) |
| Results (RQ2, RQ3) | ~4 p. | Observability vs R; shadows (H1); **verifiability gap (H2, main figure)**; sensitivity (H3) |
| Discussion | ~1 p. | What the bound means for detectors; spoof-or-vanish argument (no experiment); limitations |
| Conclusion | ~0.5 p. | Takeaways; follow-up with measured RSSI |
| Artifact availability | few lines | Repository, DOI |
| References | ~1.5 p. | — |

### Planned figures and tables

| ID | Content | Supports |
|----|---------|----------|
| Fig. scenario | RoI, domain, sites by operator, drone-track density | Method |
| Tab. G0 | Cleaning log v2 (+ v1 failure noted) | Gate |
| Tab. roles | Rows per message, AGL by role, drone–pilot distance (aggregates) | RQ1 |
| Fig. holds | CDF of position hold durations | RQ1 |
| Tab. parameters | Every parameter → value → source/assumption | Method |
| Fig. observability | Observable fraction (k = 1…4) vs R, per scenario | RQ2 |
| Fig. shadows | Paired shadow fractions, consortium vs best operator; window durations | H1 |
| **Fig. verifiability gap** | Observable vs V3 vs V4 vs R, per scenario | **H2, RQ3 (main)** |
| Fig. sensitivity | Tornado of the V3 fraction and the consortium gain | H3 |

## Adding an experiment

Before: question/hypothesis in `research.md`; metric implemented with a synthetic test; config in `experiments/configs/`; G0 and G2 green; pilot with small N. Running: clean tree, `run.py`, check `results/{exp_id}/{timestamp}/`. After: `make analysis`, write from generated outputs, update the claim → evidence matrix.

## Provenance of each run

```yaml
exp_id: blockO_obs
scenario: interlagos_consortium
channel: { family: c1_generic, eta: 2.2, shadow_sigma_db: 6.0, shadow_dcorr_m: ⚠, sniffer_sens_dbm: -95, eirp_dbm: 20, sniffer_height_m: 30 }
stage_a: { rules_version: v2, samples_sha256: ⚠, g0: PASS }
git_commit: ⚠
git_dirty: false
seeds: [0..19]
inputs: { anatel_sha256: 311c85de…, dem_sha256: 00b3d678…, roi_sha256: 74369989…, domain_sha256: db68a6cb… }
outputs: { observations_sha256: ⚠ }
discarded: []
```

> **Current state (16 Oct 2026):** scope changed to observability + verifiability bound. Stage A v2 implemented with 28 tests (commit `bea7097`). G0-v1 failed on C9 (3.55%) and is recorded; **G0-v2 PASS** (runs `20261016T213222Z` and `…213229Z`, identical tables). Next: Stage B (channel). Blocking: BM-1 (C2 parameters), BM-8 (γ), BM-28 (questions to the data provider). BM-29 resolved (CRLB criterion).

## Using these files in Kiro

`research.md`, `methods.md` and `structure.md` stay at the repository root; `.kiro/steering/` files are thin wrappers that pull them with `#[[file:...]]` (product → research, always; structure → structure, always; tech → methods, fileMatch on code; paper → writing conventions, fileMatch on `paper/**`). Kiro reads `AGENTS.md`.

**Specs, in order:** `stage-a-data` (done, v2) → `stage-b-channel` (G2) → `analysis-observability` (RQ2, H1) → `analysis-verifiability` (RQ3, H2) → `characterization` (RQ1) → `sensitivity` (H3) → `paper`. Each spec's requirements cite the RQ/hypothesis, gate and T-numbers it serves.
