# AGENTS.md — cs-rid-spoofing (Remote ID observability, SBRC 2027)

Read `.kiro/steering/research.md` (what/why), `.kiro/steering/methods.md` (how) and `.kiro/steering/structure.md` (where, golden rules) before any non-trivial task. They are the source of truth; this file only lists the rules that must never be broken.

**Scope (16 Oct 2026):** observability of the existing cellular grid for Remote ID + the verifiability upper bound (V3/V4) + data characterization. **Out of scope:** detectors, attackers, legacy pipeline, A3P. Do not create `legacy/`, `src/drs/attacks/` or `analysis/detectors/`.

## Non-negotiable rules
1. `src/drs/` (stages A–B) never imports `analysis/`.
2. Altitude is converted only in `src/drs/data/agl.py` (anchored AGL, rules v2). The MSL column is dropped afterwards.
3. One receiver per unique site (109 sites), never per ANATEL station record. Sites are never clipped by the RoI.
4. Unheard (sample, candidate site) pairs are recorded, never dropped.
5. Parameters only in `experiments/configs/*.yaml`, each channel constant with its source. No magic numbers.
6. Seeds explicit and listed; never from the clock. Time via `.dt.total_seconds()`.
7. No result number typed by hand in figures, tables or the paper.
8. **Privacy:** raw serials only in `data/external/flights/raw/`; pilot/home positions only in `data/interim/` (both git-ignored); the published track is drone-only; figures never show pilot or home locations; the HMAC key (`DSV2_HMAC_KEY`) is never printed, logged or written.
9. Never change a threshold or rule after seeing data to make a gate pass. A failing gate stops the work and is reported.
10. Git only from WSL; never `git add --renormalize` on `data/`. A run with `-dirty` is exploratory.

## Working style
- Plan first; small steps; `pytest -q` before declaring a task done. Tests are the contract.
- Every task names the RQ/hypothesis (RQ1–RQ3, H1–H3), gate (G0, G2) and T-numbers it serves.
- Commits must not include unrelated working-tree changes. Code, comments and commits in English; Conventional Commits.
