# F3 bounds, descriptive aggregates, and public-result privacy

**Status:** proposed design for review  
**Date:** 2026-10-17  
**Scope:** analysis and presentation only. No change to Stage A, channel generation, hypotheses, thresholds, or H2's pre-registered test.

## Purpose

Strengthen F3 so it distinguishes geometric non-verifiability from receiver sensitivity, add the descriptive aggregates required by Table F1 and Section 4, and ensure public artifacts do not reveal operator identities in content or paths.

H2 remains tested exactly as pre-registered: the mean per-flight gap between heard and V3 at the reference condition. Pooled-time, per-drone, dominant-drone, and leave-one-out results are descriptive and must be labelled as such in tables, macros, captions, and prose.

## Definitions

For a sample, let `J_in` be the RSS Fisher information from heard links represented in the truncated simulation. For every known inventory site beyond `r_max_m`, construct its exact optimistic contribution

\[
J_j = b^2 \frac{\Delta_j\Delta_j^T}{d_j^4},
\]

where `Delta_j` is the horizontal displacement from the drone to site `j`, `d_j` is the 3D distance used by the channel, and `b` is the RSS-position Fisher coefficient already used by the CRLB implementation.

The inventory-bounded optimistic information is

\[
J_{opt}=J_{in}+\sum_{j\in inventory,\ d_j>r_{max}}J_j.
\]

All known inventory sites beyond `r_max_m` participate, regardless of their distance from the sample. The documented cut polygon establishes inventory completeness inside the polygon; the minimum sample-to-edge distance is not a cutoff for known sites.

The inventory-bounded optimistic sample decision is:

- `0` only if fewer than three possible receivers exist after counting all known omitted sites, or if `trace(inv(J_opt)) > D^2`;
- `1` otherwise, including numerically unresolved cases.

This convention makes the result an upper bound on V3 within the known inventory. The current truncated V3 remains the lower bound.

## Unknown sites beyond the cut polygon

Unknown sites are not assigned a density. Instead, report how many optimally placed sites beyond the inventory edge would be required before verification can no longer be ruled out.

Let `lambda_1` and `lambda_2` be the eigenvalues of `J_opt`. Find the smallest `c_star >= 0` satisfying

\[
\operatorname{tr}(J_{opt}+c^\star I)^{-1}\le D^2.
\]

`c_star` is the non-negative solution of

\[
D^2x^2 + (D^2(\lambda_1+\lambda_2)-2)x
+ D^2\lambda_1\lambda_2-(\lambda_1+\lambda_2)=0.
\]

If `J_opt` already satisfies the CRLB criterion, `c_star = 0`. Degenerate and near-singular cases must use a numerically stable monotone root solution or a validated closed form; NaN must never silently become zero.

For sample-to-cut-polygon distance `d_edge`, define

\[
n^\star_{info}=\left\lceil c^\star d_{edge}^2/b^2\right\rceil.
\]

The receiver-count requirement is

\[
n^\star_{count}=\max(0,3-n_{possible}),
\]

and the reported lower bound is

\[
n^\star=\max(n^\star_{info},n^\star_{count}).
\]

This is an inventory-external lower bound: fewer than `n_star` unknown sites beyond the polygon cannot make the sample verifiable even under isotropically optimistic information. It does not claim such sites exist.

## F3 outputs and figure

At `R = 1000 m`, compute per sample and then time-aggregate per flight/session and seed:

- truncated V3 lower bound;
- inventory-bounded optimistic V3 upper bound;
- `n_star` for unknown sites beyond the cut polygon.

Average seeds using the same order as the existing V3 pipeline. The resulting mechanism table must contain explicit lower/upper columns and retain `session_id` and pseudonymized `uas_id`, without coordinates.

The F3 figure keeps the geometric x-coordinate, median distance to the third-nearest scenario site. For each flight at `R = 1000 m`, draw a vertical segment from V3 lower to V3 upper. The `R = 200 m` point remains the reference result. The legend must distinguish:

- reference V3 at `R = 200 m`;
- truncated lower bound at `R = 1000 m`;
- inventory-bounded optimistic upper bound at `R = 1000 m`;
- inventory-edge limitation.

The x-axis must leave visible space after the `1000` label.

Predefine a descriptive macro for the fraction of flights satisfying both:

- median third-site distance greater than `200 m`;
- inventory-bounded V3 upper bound at `R = 1000 m` below `0.1`.

Also freeze the minimum session-level `n_star` among those flights, with wording that it is a lower bound on additional unknown sites beyond the documented cut polygon.

## Descriptive aggregates

Compute all values from per-sample indicators and `time_weights_s`, not from map cells. Average seeds before aggregating flight time.

For the consortium at `R = 200 m`, freeze:

- total flight time;
- median session duration;
- pooled-time heard fraction O1;
- pooled-time V3 fraction;
- pooled-time gap `O1 - V3`;
- mean per-drone heard fraction;
- mean per-drone V3 fraction;
- per-drone gap, computed within the same aggregation;
- dominant drone's share of total flight time;
- dominant drone's V3;
- pooled O1, pooled V3, and their gap after excluding the dominant drone;
- number of drones whose V3 is below `0.5`;
- typical interval between position changes.

A drone's V3 is defined as the time-weighted mean of its flights' per-sample V3 indicators, in the consortium at `R = 200 m`, after averaging seeds at the prescribed stage.

Repeat pooled O1, pooled V3, same-aggregation gap, per-drone O1, and per-drone V3 for each operator and for `R in {100, 200} m`.

Confidence intervals use the existing paired cluster bootstrap by `uas_id`. O1 and V3 must be resampled together so the gap CI preserves pairing.

Every new result is marked `descriptive`. No p-value or hypothesis decision is attached. The H2 macros and test remain unchanged.

`h2S_sigma4_gap` remains intentionally absent until `blockS_sigma4/hypotheses/h2.csv` exists. Its unresolved `\ds` expansion must remain visible.

## Privacy boundary

Operator aliasing must occur when public analysis results are written, not only during freeze formatting.

Public outputs must use:

- `Operator A`, `Operator B`, `Operator C` in display text;
- `opA`, `opB`, `opC` in keys and paths;
- no raw operator names in scenario columns, selectors, source paths, filenames, directory names, TeX, Markdown, CSV, JSON, or extracted PDF text.

Internal raw-name artifacts may remain only in the private repository and must not appear in the public manifest.

The public freeze sanitizes `selector`, `source`, section text, and path components using the private mapping. The private mapping remains under the ignored `experiments/configs/local/` path.

The privacy test:

1. loads forbidden raw names from the private mapping file;
2. skips only when that private file is absent, as in the public/CI checkout;
3. scans contents and relative paths of every artifact selected by the public manifest;
4. scans `.tex` sources and text extracted from every public PDF;
5. reports filenames only, never forbidden values.

Git-history scanning is BM-40 and remains a separate publication gate. No implementation in this scope rewrites history.

## Presentation

Use the shared figure style for all paper figures:

- 10 pt for axis labels and titles;
- 9 pt for ticks, annotations, and legends;
- 15 cm target width;
- shared scenario colors, dashes, and markers;
- explicit clipping/layout tests where practical.

For map PDFs, rasterize only the spatial cell/hexagon collection at 300 dpi. Text, sites, RoI, inventory boundary, axes, and legend remain vector elements.

Produce a final vector teaser. Verify that the shadow-reduction legend and all other legends fit at 15 cm.

## Tests

### CRLB and upper bound

- Adding exact known-site Fisher matrices preserves Loewner order.
- Inventory-bounded optimistic sample V3 is never below truncated sample V3.
- A synthetic case with known sites beyond `r_max_m` matches the untruncated all-known-sites result.
- Known omitted sites use their exact directions and 3D distances.
- All known inventory sites beyond `r_max_m` are included.
- The decision changes correctly immediately above and below `D`.
- Fewer than three possible receivers yields optimistic decision zero.
- Numerically unresolved cases yield upper decision one and an explicit diagnostic flag.

### Unknown-site lower bound

- `c_star = 0` when `J_opt` already satisfies the criterion.
- The quadratic/root result agrees with direct evaluation of `trace(inv(J_opt + cI))`.
- `n_star` is monotone non-decreasing with `d_edge`.
- `n_star` respects the receiver-count floor.
- A synthetic isotropic construction with `n_star - 1` sites cannot pass, while the bound is reached at `n_star` within declared integer-rounding tolerance.

### Descriptive aggregation

- Synthetic known-answer cases verify pooled-time, per-drone, dominant-share, leave-one-out, below-0.5 count, and paired gap.
- Changing session durations changes pooled-time results but not equal-drone weighting.
- O1 and V3 gap uses values from the same bootstrap draw and aggregation.
- Seeds are averaged before time/drone aggregation.

### Privacy

- Forbidden names are loaded from the ignored private mapping, never literals in tracked tests.
- Public path and content scanning catches a forbidden name in each supported artifact class.
- PDF scanning uses extracted text and reports only the offending filename.
- Without the private mapping, the raw-name test is skipped.
- Public freeze selectors and source paths contain aliases only.

### Figures

- F3 emits both PDF and PNG and includes lower/upper R=1000 columns.
- Map PDF contains a rasterized spatial collection while text remains vector.
- Expected dimensions and font sizes are applied through the shared style.

## Generated artifacts

The analysis stage produces reviewable tables before freeze:

- descriptive aggregates with definitions and CIs;
- F3 per-session lower/upper bounds and `n_star`;
- F3 summary;
- regenerated figures.

The freeze stage consumes these tables and writes sourced entries to `numbers.csv`, `numbers.tex`, and the public freeze report. It never recomputes metrics.

## Completion criteria

- All tests pass.
- Existing H2 values and decisions are byte-identical or numerically identical to their frozen inputs.
- New macros have a source file, selector, and input SHA-256.
- F3 reports both bounds and the inventory-external `n_star` limitation.
- Public-manifest scan finds no raw operator name in content or path.
- PDF text scan finds no raw operator name.
- `h2S_sigma4_gap` remains visibly unresolved until its block exists.
- No Stage A, channel, threshold, or hypothesis code changes.
