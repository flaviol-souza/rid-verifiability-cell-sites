# Digital Shadows v2 — Agent Context

The repository studies physical verification of Remote ID positions using passive 2.4 GHz sniffers at ANATEL cell sites and real Interlagos trajectories.

Read `research.md`, `methods.md`, and `structure.md` before non-trivial work. Stages A–C live under `src/drs/`; analysis stages D–E live under `analysis/`. The simulator never imports analysis, detectors never receive truth, and altitude is converted only in `src/drs/data/agl.py`.

Use configuration files as the source of experiment parameters. Preserve deterministic seeds, provenance, hashes, cleaning logs, and three-state outcomes. Do not alter thresholds or rules after observing results. Raw flight identifiers remain under the ignored raw-data directory until HMAC anonymization produces the published flight input.

Run `pytest -q` before completing code changes. Keep commits focused and do not include unrelated working-tree changes.
