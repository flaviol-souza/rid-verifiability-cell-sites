# F3 Bounds and Descriptive Freeze Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add inventory-bounded V3 intervals, unknown-site lower bounds, descriptive time/drone aggregates, and end-to-end operator de-identification to the public result pipeline.

**Architecture:** Pure numerical functions live in `analysis/verifiability.py`; aggregation lives in a focused `analysis/descriptive.py`; mechanism and figure runners consume those outputs; `run_freeze.py` only freezes sourced tables. Public-output sanitization happens at write boundaries through `analysis/alias.py`, while the private operator mapping remains ignored.

**Tech Stack:** Python 3.11+, NumPy, pandas, SciPy, matplotlib, pytest, pdftotext.

**Spec:** `docs/superpowers/specs/2026-10-17-f3-bounds-descriptive-freeze-design.md`

## Global Constraints

- H2 remains the pre-registered mean per-flight gap test; all new pooled/drone/leave-one-out values are descriptive.
- No change to Stage A, channel generation, thresholds, hypotheses, or existing H2 decisions.
- Known omitted sites use exact Fisher matrices and include every known inventory site beyond `r_max_m`.
- Unknown external sites receive no density assumption; report only the lower bound `n_star`.
- Public outputs use Operator A/B/C and opA/opB/opC in content and paths.
- The private alias mapping stays under ignored `experiments/configs/local/`.
- `h2S_sigma4_gap` remains unresolved until its block exists.
- Tests precede production changes; each task gets a focused commit.

## Review Focus

- Singular or nearly singular Fisher matrices must produce an optimistic upper decision, an explicit diagnostic, and no accidental zero.
- Samples outside or on the cut-polygon boundary must not yield a falsely finite unknown-site requirement.
- Known sites beyond `r_max_m` but farther than the minimum edge distance must still contribute to `J_opt`.
- Duplicate/resampled `uas_id` clusters must preserve O1/V3 pairing in bootstrap draws.
- Raw operator names embedded in path components or PDF metadata/text must block public export.

---

### Task 1: Stabilize and test public operator sanitization

**Files:**
- Modify: `analysis/alias.py`
- Modify: `experiments/run_summary.py`
- Modify: `experiments/run_map.py`
- Modify: `experiments/run_mechanism.py`
- Modify: `experiments/run_freeze.py`
- Modify: `tools/export_public.py`
- Test: `tests/test_export_public.py`
- Test: `tests/test_stage_f.py`

**Interfaces:**
- Consumes: private alias mapping loaded by `load_alias(cfg: dict, root: Path) -> dict[str, str]`.
- Produces: `sanitize(text: str, alias: dict[str, str], style: str) -> str` and public paths/content without raw names.

- [ ] **Step 1: Write failing tests for path, selector, TeX, CSV, Markdown, and PDF-name scanning**

Tests read forbidden names from a temporary private mapping, assert no literal raw names appear in tracked test source, and verify filename-only failure reports. Add a skip case when the mapping file is absent.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_export_public.py tests/test_stage_f.py -q`  
Expected: failures identify unsanitized selector/source/path or missing path scan.

- [ ] **Step 3: Implement sanitization at result-write boundaries**

Sanitize scenario values, selectors, source paths, filenames, directory names, TeX, Markdown, and public CSVs. Keep internal raw-name inputs private. Extend `export_public.py` to scan manifest-selected relative paths, contents, `.tex`, and extracted PDF text.

- [ ] **Step 4: Run focused tests and full suite**

Run: `python -m pytest tests/test_export_public.py tests/test_stage_f.py -q && python -m pytest -q`  
Expected: all pass; private-mapping-dependent scan runs locally.

- [ ] **Step 5: Commit**

```bash
git add analysis/alias.py experiments/run_summary.py experiments/run_map.py experiments/run_mechanism.py experiments/run_freeze.py tools/export_public.py tests/test_export_public.py tests/test_stage_f.py
git commit -m "fix(privacy): de-identify public result content and paths"
```

### Task 2: Add descriptive aggregation with paired bootstrap

**Files:**
- Create: `analysis/descriptive.py`
- Create: `tests/test_descriptive.py`
- Modify: `experiments/run_summary.py`

**Interfaces:**
- Consumes: per-session/per-seed metrics and Stage A sample timestamps.
- Produces: `descriptive_aggregates(metrics, samples, family, scenarios, ranges_m, scale_m, seed, n_boot) -> tuple[pd.DataFrame, pd.DataFrame]`.

- [ ] **Step 1: Write synthetic known-answer tests**

Cover pooled-time O1/V3/gap, equal-drone O1/V3/gap, dominant time share, dominant V3, leave-one-out, count below 0.5, total duration, median session duration, and position-change interval. Assert seeds are averaged before aggregation and paired bootstrap resamples O1/V3 together.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_descriptive.py -q`  
Expected: import/function missing.

- [ ] **Step 3: Implement pure aggregation functions**

Use `analysis.observability.time_weights_s`; define per-drone V3 as the time-weighted mean over that drone's flights at consortium/R=200 m. Return one aggregate table and one per-drone table with explicit `descriptive=True`.

- [ ] **Step 4: Integrate into `run_summary.py`**

Write `summary/descriptive.csv` and `summary/descriptive_per_drone.csv` with LF endings. Include consortium and each operator at R=100/200 m.

- [ ] **Step 5: Verify and commit**

Run: `python -m pytest tests/test_descriptive.py -q && python -m pytest -q`  
Expected: all pass.

```bash
git add analysis/descriptive.py experiments/run_summary.py tests/test_descriptive.py
git commit -m "analysis: add descriptive time and drone aggregates"
```

### Task 3: Implement exact inventory-bounded optimistic CRLB

**Files:**
- Modify: `analysis/verifiability.py`
- Modify: `analysis/geometry.py`
- Create: `tests/test_verifiability_bounds.py`

**Interfaces:**
- Produces: `inventory_bounded_v3_bounds(...) -> pd.DataFrame` with per-sample lower decision, upper decision, `sigma_h_opt_m`, possible receiver count, and diagnostic status.
- Produces: `minimum_external_sites(J_opt, d_edge_m, fisher_b, scale_m, n_possible) -> int | float`.

- [ ] **Step 1: Write failing matrix and geometry tests**

Assert Loewner monotonicity; upper decision never below truncated decision; exact agreement with an untruncated synthetic inventory; inclusion of all known sites beyond `r_max_m`; correct decisions around D; receiver-count floor; unresolved numerical case becomes upper=1 with diagnostic.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_verifiability_bounds.py -q`  
Expected: missing interfaces.

- [ ] **Step 3: Implement exact known-site information**

Reuse the channel's 3D distance and the existing Fisher coefficient. Add exact directional matrices for every known site outside `r_max_m`; do not cut them at `d_edge_m`.

- [ ] **Step 4: Implement stable `c_star` and `n_star`**

Solve the monotone trace-inverse condition robustly, ceil the information bound, and take the maximum with `3 - n_possible`. Reject non-positive/non-finite `d_edge_m`; preserve diagnostics.

- [ ] **Step 5: Verify and commit**

Run: `python -m pytest tests/test_verifiability_bounds.py -q && python -m pytest -q`  
Expected: all pass.

```bash
git add analysis/verifiability.py analysis/geometry.py tests/test_verifiability_bounds.py
git commit -m "analysis: add inventory-bounded V3 upper bound and external-site lower bound"
```

### Task 4: Produce F3 lower/upper tables and figure

**Files:**
- Modify: `experiments/run_mechanism.py`
- Modify: `analysis/figstyle.py`
- Modify: `tests/test_stage_f.py`

**Interfaces:**
- Consumes: Task 3 bound functions and block O R=200/R=1000 results.
- Produces: mechanism session/summary columns for R=1000 lower/upper V3 and `n_star`; regenerated `fig_mechanism`.

- [ ] **Step 1: Write failing integration tests**

Assert output columns exist; each row satisfies `V3_lower <= V3_upper`; vertical intervals are represented; the descriptive fraction for `d3_median_m > 200` and upper V3 `< 0.1` is emitted; x-axis includes padding beyond 1000.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_stage_f.py -q`  
Expected: missing F3 bound columns/summary.

- [ ] **Step 3: Implement mechanism aggregation and figure**

Average seeds in the existing order. Draw R=200 reference points plus R=1000 vertical lower/upper segments. Label R=1000 as inventory-bounded and declare the external-inventory limitation.

- [ ] **Step 4: Verify and commit**

Run: `python -m pytest tests/test_stage_f.py -q && python -m pytest -q`  
Expected: all pass.

```bash
git add experiments/run_mechanism.py analysis/figstyle.py tests/test_stage_f.py
git commit -m "analysis: show inventory-bounded V3 intervals in F3"
```

### Task 5: Freeze sourced descriptive and F3 numbers

**Files:**
- Modify: `experiments/run_freeze.py`
- Modify: `tests/test_stage_f.py`

**Interfaces:**
- Consumes: `descriptive.csv`, F3 mechanism summary/session tables.
- Produces: sourced entries in `numbers.csv`, `numbers.tex`, and public freeze report.

- [ ] **Step 1: Write failing freeze tests**

Assert new keys exist with source and selector; same-aggregation gaps are used; F3 fraction and minimum `n_star` are sourced; selectors/paths are alias-only; `h2S_sigma4_gap` is absent.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_stage_f.py -q`  
Expected: missing keys.

- [ ] **Step 3: Extend freeze as a reader only**

Add descriptive and F3 keys from generated tables. Do not recompute metrics. Preserve SHA-256 recording and deterministic output.

- [ ] **Step 4: Verify and commit**

Run: `python -m pytest tests/test_stage_f.py -q && python -m pytest -q`  
Expected: all pass and repeated freeze hashes match.

```bash
git add experiments/run_freeze.py tests/test_stage_f.py
git commit -m "feat(freeze): add sourced descriptive and F3 bound macros"
```

### Task 6: Apply final figure typography and vector/raster policy

**Files:**
- Modify: `analysis/figstyle.py`
- Modify: `analysis/make_figures.py`
- Modify: `experiments/run_map.py`
- Modify: `analysis/fig_scenario.py`
- Test: `tests/test_stage_d.py`
- Test: `tests/test_stage_f.py`

**Interfaces:**
- Produces: 15 cm figures with 10 pt main text, 9 pt secondary text, vector teaser, and map PDF with only spatial cells rasterized at 300 dpi.

- [ ] **Step 1: Write failing presentation-contract tests**

Assert shared sizes, output dimensions, map collection rasterization, PDF/PNG existence, and no legend clipping regression.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_stage_d.py tests/test_stage_f.py -q`  
Expected: typography/rasterization assertions fail.

- [ ] **Step 3: Apply shared style and map rasterization**

Set sizes only in `figstyle.py`; use shared constants everywhere. Set `rasterized=True` only on the map cell collection. Keep text/sites/RoI/inventory boundary vector.

- [ ] **Step 4: Verify and commit**

Run: `python -m pytest tests/test_stage_d.py tests/test_stage_f.py -q && python -m pytest -q`  
Expected: all pass.

```bash
git add analysis/figstyle.py analysis/make_figures.py experiments/run_map.py analysis/fig_scenario.py tests/test_stage_d.py tests/test_stage_f.py
git commit -m "style(figures): finalize paper typography and vector outputs"
```

### Task 7: Regenerate, audit, and freeze without changing inputs

**Files:**
- Generated only: existing result directories and public freeze outputs.
- No production-code changes unless a test-first bugfix is required.

**Interfaces:**
- Consumes: committed Tasks 1–6 and existing block outputs.
- Produces: reviewed figures, descriptive tables, F3 tables, and deterministic public freeze.

- [ ] **Step 1: Require a clean tracked tree and record input hashes**

Run: `git status --porcelain --untracked-files=no`  
Expected: empty.

- [ ] **Step 2: Regenerate analysis-only outputs**

Run summary, mechanism, map, and freeze commands against existing blocks. Do not run Stage A or channel blocks.

- [ ] **Step 3: Verify deterministic freeze**

Run freeze twice; compare SHA-256 for `numbers.csv`, `numbers.tex`, and public freeze report.  
Expected: identical hashes.

- [ ] **Step 4: Run privacy gates**

Scan manifest-selected paths/content, TeX, and extracted PDF text using the private mapping.  
Expected: zero findings. Record BM-40 as still pending if history has not been cleaned.

- [ ] **Step 5: Run final suite**

Run: `python -m pytest -q`  
Expected: all pass.

- [ ] **Step 6: Report without committing generated private results**

Report source tables, macros, hashes, figure paths, tests, descriptive/H2 distinction, unresolved sigma4 macro, and BM-40 status.
