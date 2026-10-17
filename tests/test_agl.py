import pandas as pd
import pytest

from conftest import DEM_ELEV_M
from drs.data import agl


def test_agl_is_msl_minus_dem_and_msl_column_is_dropped(workspace):
    root, cfg = workspace
    df = pd.DataFrame({"lat": [-23.70], "lon": [-46.70], "alt": [800.0]})
    out = agl.add_agl(df, str(root / cfg["stage_a"]["paths"]["dem"]))
    assert out["agl_m"].iloc[0] == pytest.approx(800.0 - DEM_ELEV_M)
    assert "alt" not in out.columns


def test_outside_dem_is_an_error(workspace):
    root, cfg = workspace
    df = pd.DataFrame({"lat": [-10.0], "lon": [-40.0], "alt": [800.0]})
    with pytest.raises(agl.DemCoverageError):
        agl.add_agl(df, str(root / cfg["stage_a"]["paths"]["dem"]))


def test_alt_is_only_converted_in_agl_module():
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "src" / "drs"
    offenders = [p for p in src.rglob("*.py") if p.name != "agl.py" and '"agl_m"] =' in p.read_text()]
    assert not offenders, f"AGL computed outside agl.py: {offenders}"
