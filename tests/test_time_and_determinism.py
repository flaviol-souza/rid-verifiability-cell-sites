import hashlib

import pandas as pd

from drs.data import stage_a


def test_durations_independent_of_datetime_unit():
    for unit in ("ns", "us", "s"):
        t = pd.Series(pd.to_datetime(["2025-11-08T18:00:00Z", "2025-11-08T18:02:00Z"], utc=True)).astype(f"datetime64[{unit}, UTC]")
        assert t.diff().dt.total_seconds().iloc[1] == 120.0


def _hashes(root, cfg):
    p = cfg["stage_a"]["paths"]
    files = [root / p["flights_anon"]] + [root / p["interim_dir"] / f for f in ("samples.parquet", "sites.parquet", "cleaning_log.csv")]
    return {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in files}


def test_stage_a_is_byte_deterministic(workspace):
    root, cfg = workspace
    stage_a.run(cfg, root); h1 = _hashes(root, cfg)
    stage_a.run(cfg, root); h2 = _hashes(root, cfg)
    assert h1 == h2
