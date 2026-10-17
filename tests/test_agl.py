import pandas as pd
import pytest

from conftest import DEM_ELEV_M
from drs.data import agl


def test_agl_is_msl_minus_dem_and_msl_column_is_dropped(workspace):
    root, cfg = workspace
    df = pd.DataFrame({"session_id": ["s"], "lat": [-23.70], "lon": [-46.70], "alt": [800.0]})
    out = agl.add_agl(df, str(root / cfg["stage_a"]["paths"]["dem"]))
    assert out["agl_m"].iloc[0] == pytest.approx(800.0 - DEM_ELEV_M)
    assert out["agl_anchor"].iloc[0] == "none"
    assert "alt" not in out.columns


def test_outside_dem_is_an_error(workspace):
    root, cfg = workspace
    df = pd.DataFrame({"session_id": ["s"], "lat": [-10.0], "lon": [-40.0], "alt": [800.0]})
    with pytest.raises(agl.DemCoverageError):
        agl.add_agl(df, str(root / cfg["stage_a"]["paths"]["dem"]))


def test_alt_is_only_converted_in_agl_module():
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "src" / "drs"
    offenders = [p for p in src.rglob("*.py") if p.name != "agl.py" and '"agl_m"] =' in p.read_text()]
    assert not offenders, f"AGL computed outside agl.py: {offenders}"


def test_anchor_priority_home_then_pilot(workspace):
    root, cfg = workspace
    dem = str(root / cfg["stage_a"]["paths"]["dem"])
    df = pd.DataFrame({"session_id": ["a", "b", "c"], "lat": -23.70, "lon": -46.70, "alt": 800.0})
    refs = pd.DataFrame({"session_id": ["a", "a", "b"], "role": ["home", "pilot", "pilot"],
                         "lat": -23.70, "lon": -46.70, "alt": [DEM_ELEV_M + 6, DEM_ELEV_M + 9, DEM_ELEV_M + 7]})
    out = agl.add_agl(df, dem, refs).set_index("session_id")
    assert out.loc["a", "agl_anchor"] == "home" and out.loc["a", "agl_m"] == pytest.approx(800 - DEM_ELEV_M - 6)
    assert out.loc["b", "agl_anchor"] == "pilot" and out.loc["b", "agl_m"] == pytest.approx(800 - DEM_ELEV_M - 7)
    assert out.loc["c", "agl_anchor"] == "none" and out.loc["c", "agl_m"] == pytest.approx(800 - DEM_ELEV_M)
    assert (out["agl_dem_m"] == 800 - DEM_ELEV_M).all()


def test_pipeline_anchors_each_session(workspace):
    from conftest import HOME_ALT, OPER_ALT
    from drs.data import stage_a
    root, cfg = workspace
    smp = stage_a.run(cfg, root)["samples"]
    by = smp.groupby("uas_id")["agl_anchor"].first().value_counts().to_dict()
    assert by == {"home": 1, "ground_ref": 1, "none": 2}
    home_rows = smp[smp["agl_anchor"] == "home"]
    assert home_rows["agl_m"].iloc[0] == pytest.approx(800 - HOME_ALT)
    assert smp.loc[smp["agl_anchor"] == "ground_ref", "agl_m"].iloc[0] == pytest.approx(800 - OPER_ALT)
