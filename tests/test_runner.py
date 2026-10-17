import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]


def test_runner_writes_g0_table_and_provenance(workspace):
    root, cfg = workspace
    (root / "experiments/configs").mkdir(parents=True)
    (root / "experiments/configs/reference.yaml").write_text(yaml.safe_dump(cfg))
    r = subprocess.run([sys.executable, str(REPO / "experiments/run_stage_a.py"), "--root", str(root)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    runs = list((root / cfg["stage_a"]["paths"]["results_dir"]).iterdir())
    assert len(runs) == 1
    assert {"g0_table.csv", "provenance.yaml", "cleaning_log.csv"} <= {f.name for f in runs[0].iterdir()}
    prov = yaml.safe_load((runs[0] / "provenance.yaml").read_text())
    assert prov["G0"] == "PASS" and len(prov["inputs_sha256"]["dem"]) == 64
    assert cfg["stage_a"]["hmac_key_env"] in prov["config"]["stage_a"]["hmac_key_env"]
    from conftest import TEST_KEY_HEX
    assert TEST_KEY_HEX not in (runs[0] / "provenance.yaml").read_text()   # key value never written
