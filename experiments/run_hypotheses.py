"""H1–H3 from a block output (session_metrics.parquet). Criteria come only from the config.

Usage: python experiments/run_hypotheses.py --config experiments/configs/reference.yaml --blocks results/stage_b/blockO
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis import hypotheses as hy


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="experiments/configs/reference.yaml")
    ap.add_argument("--root", default=".")
    ap.add_argument("--blocks", required=True)
    a = ap.parse_args()
    root = Path(a.root).resolve()
    b = yaml.safe_load((root / a.config).read_text())["stage_b"]
    if b.get("range_ref_m") is None:
        print("ERROR: stage_b.range_ref_m is not set (BM-31). Fix it in the config before testing H2.", file=sys.stderr)
        return 2
    blk = root / a.blocks
    man = pd.read_csv(blk / "manifest.csv")
    sm = hy.session_means(pd.read_parquet(blk / "session_metrics.parquet"))
    out = blk / "hypotheses"; out.mkdir(exist_ok=True)
    fams = sorted(sm["family"].unique())
    pd.concat([hy.h1_cooperation(sm, f, k) for f in fams for k in (1, 3)]).to_csv(out / "h1.csv", index=False, lineterminator="\n")
    pd.DataFrame([hy.h2_gap(sm, f, float(b["range_ref_m"]), b["verif_scale_ref_m"], b["h2_min_effect"], lvl)
                  for f in fams for lvl in (3, 4)]).to_csv(out / "h2.csv", index=False, lineterminator="\n")
    hy.h3_ranking(sm, b["verif_scale_ref_m"]).to_csv(out / "h3.csv", index=False, lineterminator="\n")
    trunc = man.groupby(["family", "range_m"])["truncated"].first().reset_index()
    trunc.to_csv(out / "truncated_cells.csv", index=False, lineterminator="\n")
    print(f"H1/H2/H3 written to {out.relative_to(root)} (truncated ranges are lower bounds: see truncated_cells.csv)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
