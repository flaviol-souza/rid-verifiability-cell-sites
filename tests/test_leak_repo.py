"""R1.6 — no raw serial in any git-tracked file. Runs only in the real repo (skips when raw/ is absent).
The serial list is read from raw/, never from a constant in the code."""
import subprocess
from pathlib import Path

import pandas as pd
import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((REPO / "experiments/configs/reference.yaml").read_text())
RAW = REPO / CFG["stage_a"]["paths"]["flights_raw"]
# Literal non-identifying values present in the raw column (not serial numbers). Keep this list short and justified.
NOT_SERIALS = set(CFG["stage_a"].get("leak_test_ignore", []))


@pytest.mark.skipif(not RAW.exists(), reason="raw flight logs not present (CI / synthetic env)")
def test_no_raw_serial_in_tracked_files():
    serials = set(pd.read_csv(RAW, dtype={"flight_id": str})["flight_id"].dropna().unique()) - NOT_SERIALS
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True).stdout.split(b"\0")
    hits = []
    for rel in filter(None, tracked):
        f = REPO / rel.decode()
        if not f.is_file() or f.stat().st_size > 50_000_000:
            continue
        data = f.read_bytes()
        hits += [(rel.decode(), s) for s in serials if s.encode() in data]
    # print only file names and pseudonym-safe info, never the serial itself
    assert not hits, f"raw serials found in {len(hits)} place(s): {sorted({h[0] for h in hits})}"
