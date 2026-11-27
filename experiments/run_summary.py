"""Summary tables and figures from a block output. Run after run_blocks.py and run_hypotheses.py.

Usage: python experiments/run_summary.py --config experiments/configs/reference.yaml --blocks results/stage_b/blockO
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis import figstyle as fs  # noqa: E402
from analysis import make_figures as mf  # noqa: E402
from analysis import descriptive  # noqa: E402
from analysis import summarize  # noqa: E402

R_MAX_KEYS = ("r_max_m", "rmax_m", "candidate_radius_m", "site_radius_m")   # inventory radius (1 km)


def _trunc_from(b, root, cli_value=None, numbers=None, key=fs.RSTAR_KEY):
    """R* (BM-32): where the hatched lower-bound range starts. Priority: --r-star; the generated
    numbers.tex (value stored under `key`); the config (inventory radius + channel); else None (old
    placement) with a note -- never the midpoint between two swept ranges."""
    if cli_value is not None:
        return float(cli_value), "--r-star"
    if numbers is not None:
        v = fs.read_macro(root / numbers, key)
        if v is not None:
            return v, f"{numbers}: {key}"
    r_max = next((float(b[k]) for k in R_MAX_KEYS if b.get(k) is not None), None)
    if r_max is not None:
        ch = yaml.safe_load((root / b["channel"]).read_text())
        return fs.r_star(r_max, ch["eta"], ch["shadow_sigma_db"]), "config"
    print(f"WARNING: R* not found (--r-star, '{key}' in {numbers}, or stage_b {R_MAX_KEYS}); "
          "the hatch starts before the first truncated range instead", file=sys.stderr)
    return None, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="experiments/configs/reference.yaml")
    ap.add_argument("--root", default=".")
    ap.add_argument("--blocks", required=True)
    ap.add_argument("--numbers", default="paper/numbers.tex", help="generated macros; R* is read from it")
    ap.add_argument("--hatch-from-rstar", action="store_true",
                    help="start the hatch at R* instead of just before the first truncated range (default off: "
                         "the hatch marks the swept points that are lower bounds; R* goes in the caption)")
    ap.add_argument("--r-star", type=float, default=None, help="override R* (m); only with --hatch-from-rstar")
    ap.add_argument("--rstar-key", default=fs.RSTAR_KEY, help="key of R* in numbers.tex")
    a = ap.parse_args()
    root = Path(a.root).resolve()
    cfg = yaml.safe_load((root / a.config).read_text())
    b = cfg["stage_b"]
    from analysis.alias import check, load_alias
    alias = load_alias(cfg, root)
    blk = root / a.blocks
    tbl = pd.read_parquet(blk / "session_metrics.parquet")
    check(alias, tbl["scenario"].unique())
    man = pd.read_csv(blk / "manifest.csv")
    out = blk / "summary"; out.mkdir(exist_ok=True)
    summ = summarize.summary_table(tbl)
    summ.to_csv(out / "summary.csv", index=False, lineterminator="\n")
    samples = pd.read_parquet(root / cfg["stage_a"]["paths"]["interim_dir"] / "samples.parquet")
    for fam in sorted(tbl["family"].unique()):
        available = sorted(float(value) for value in tbl.loc[tbl["family"] == fam, "range_m"].unique())
        requested = [value for value in (100.0, 200.0) if value in available]
        if not requested and b.get("range_ref_m") is not None:
            requested = [float(b["range_ref_m"])]
        desc, desc_drones = descriptive.tables_from_pipeline(
            tbl, samples, float(cfg["stage_a"]["session_gap_s"]), fam, requested
        )
        desc.to_csv(out / f"descriptive_{fam}.csv", index=False, lineterminator="\n")
        desc_drones.to_csv(out / f"descriptive_per_drone_{fam}.csv", index=False, lineterminator="\n")
    figs = blk / "figures"
    r_star = None
    if a.hatch_from_rstar:
        r_star, src = _trunc_from(b, root, a.r_star, a.numbers, a.rstar_key)
        if r_star is not None:
            print(f"R* = {r_star:.0f} m (from {src}): start of the lower-bound hatch")
    h1p, h2p = blk / "hypotheses" / "h1.csv", blk / "hypotheses" / "h2.csv"
    h2 = pd.read_csv(h2p) if h2p.exists() else None
    ref = float(b["range_ref_m"]) if b.get("range_ref_m") is not None else None
    for fam in sorted(tbl["family"].unique()):
        trunc = sorted(man.loc[(man["family"] == fam) & man["truncated"], "range_m"].unique())
        mf.fig_observability(summ, trunc, figs, fam, alias=alias, trunc_from=r_star,
                             scale_m=b["verif_scale_ref_m"])          # (a) |S| >= 3, (b) V3 per operator
        mf.fig_verifiability_gap(summ, trunc, figs, fam, b["verif_scale_ref_m"], h2=h2, ref_range=ref,
                                 trunc_from=r_star)
        if h1p.exists():
            mf.fig_shadow_reduction(pd.read_csv(h1p), trunc, figs, fam, trunc_from=r_star)
        if ref is not None:
            summarize.per_serial_table(tbl, fam, "consortium", ref, f"V3_D{int(b['verif_scale_ref_m'])}") \
                .to_csv(out / f"per_serial_V3_{fam}.csv", index=False, lineterminator="\n")
    if h2 is not None and mf._h2_numbers(h2, sorted(tbl["family"].unique())[0], ref) is None:
        print(f"note: could not read the H2 gap at R = {ref} from {h2p.name} (columns: {list(h2.columns)}); "
              "the gap figure is labelled without numbers", file=sys.stderr)
    print(f"summary -> {out.relative_to(root)}; figures -> {figs.relative_to(root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
