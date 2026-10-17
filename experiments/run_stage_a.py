"""Run Stage A on real data and write the G0 table.

Usage (from the repo root, with DSV2_HMAC_KEY exported in the shell; never print it):
    python experiments/run_stage_a.py --config experiments/configs/reference.yaml
Exit code 0 = G0 PASS, 1 = G0 FAIL (downstream stages must not run), 2 = input/precondition error.
"""
import argparse
import datetime as dt
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import yaml

from drs.data import agl, anonymize, stage_a


def _git_commit(root: Path) -> str:
    try:
        rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root,
                               capture_output=True, text=True, check=True).stdout.strip()
        return rev + ("-dirty" if dirty else "")
    except Exception:
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="experiments/configs/reference.yaml")
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    cfg = stage_a.load_config(root / args.config)
    try:
        res = stage_a.run(cfg, root)
    except (anonymize.KeyMissingError, anonymize.PseudonymCollisionError,
            agl.DemCoverageError, stage_a.InputHashMismatch, FileNotFoundError) as e:
        print(f"PRECONDITION ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    g0 = stage_a.g0_evaluate(res["samples"], res["log"], cfg, res["domain"], res["diag"])

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = root / cfg["stage_a"]["paths"]["results_dir"] / stamp
    out.mkdir(parents=True)
    flat = {k: (v if not isinstance(v, (list, dict)) else str(v)) for k, v in g0.items() if k != "checks"}
    flat.update({f"check_{k}": v for k, v in g0["checks"].items()})
    pd.DataFrame([flat]).T.rename(columns={0: "value"}).rename_axis("metric").to_csv(out / "g0_table.csv")
    shutil.copy(root / cfg["stage_a"]["paths"]["interim_dir"] / "cleaning_log.csv", out / "cleaning_log.csv")
    p = cfg["stage_a"]["paths"]
    inputs = {k: stage_a.sha256(root / p[k]) for k in ("anatel", "dem", "roi", "domain")}
    outputs = {k: stage_a.sha256(root / v) for k, v in {
        "flights_anon": p["flights_anon"], "samples": f"{p['interim_dir']}/samples.parquet",
        "sites": f"{p['interim_dir']}/sites.parquet", "cleaning_log": f"{p['interim_dir']}/cleaning_log.csv",
        "ground_refs": f"{p['interim_dir']}/ground_refs.parquet"}.items()}
    prov = {"created_utc": stamp, "git_commit": _git_commit(root), "config_file": args.config,
            "config": cfg, "inputs_sha256": inputs, "outputs_sha256": outputs,
            "pandas": pd.__version__, "python": sys.version.split()[0], "G0": g0["G0"], "failing": g0["failing"]}
    (out / "provenance.yaml").write_text(
        yaml.safe_dump(prov, sort_keys=True, allow_unicode=True), newline="\n"
    )
    print(pd.read_csv(out / "g0_table.csv").to_string(index=False))
    print(f"\nG0 = {g0['G0']}  ->  {out.relative_to(root)}")
    if g0["G0"] == "FAIL":
        (out / "G0_FAILED.txt").write_text(
            "Failing criteria: " + ", ".join(g0["failing"]) + "\nDo not run downstream stages.\n",
            newline="\n",
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
