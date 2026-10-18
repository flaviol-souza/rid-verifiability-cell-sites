"""Summary tables and figures from a block output. Run after run_blocks.py and run_hypotheses.py.

Usage: python experiments/run_summary.py --config experiments/configs/reference.yaml --blocks results/stage_b/blockO
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis import make_figures as mf
from analysis import summarize


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="experiments/configs/reference.yaml")
    ap.add_argument("--root", default=".")
    ap.add_argument("--blocks", required=True)
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
    figs = blk / "figures"
    for fam in sorted(tbl["family"].unique()):
        trunc = sorted(man.loc[(man["family"] == fam) & man["truncated"], "range_m"].unique())
        mf.fig_observability(summ, trunc, figs, fam, alias=alias)
        mf.fig_verifiability_gap(summ, trunc, figs, fam, b["verif_scale_ref_m"])
        h1p = blk / "hypotheses" / "h1.csv"
        if h1p.exists():
            mf.fig_shadow_reduction(pd.read_csv(h1p), trunc, figs, fam)
        if b.get("range_ref_m") is not None:
            summarize.per_serial_table(tbl, fam, "consortium", float(b["range_ref_m"]), f"V3_D{int(b['verif_scale_ref_m'])}") \
                .to_csv(out / f"per_serial_V3_{fam}.csv", index=False, lineterminator="\n")
    print(f"summary -> {out.relative_to(root)}; figures -> {figs.relative_to(root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
