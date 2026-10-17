"""RQ1 tables from Stage A outputs. Writes aggregates only (no positions); safe to version.

Usage: python experiments/run_characterization.py --config experiments/configs/reference.yaml --out results/stage_c/characterization
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis import characterization as chz


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="experiments/configs/reference.yaml")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    root = Path(a.root).resolve()
    cfg = yaml.safe_load((root / a.config).read_text())
    interim = root / cfg["stage_a"]["paths"]["interim_dir"]
    tables = chz.characterize(pd.read_parquet(interim / "samples.parquet"), pd.read_parquet(interim / "ground_refs.parquet"))
    out = root / a.out
    out.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(out / f"{name}.csv", index=False, lineterminator="\n")
    print(f"{len(tables)} tables -> {out.relative_to(root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
