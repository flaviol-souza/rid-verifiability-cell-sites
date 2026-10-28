"""Visual standard of the paper's figures (analysis/figstyle.py) and of the scripts that already use it.

What is guarded:
  * one colour, one dash and one marker per scenario, none reused by another role (event zone, d*_3, R);
  * the paper label of a scenario decides its style, never its position in a list;
  * every saved PDF is byte-identical across runs (same rule as test_stage_d for the summary figures);
  * Fig. 1 (teaser) says what its caption says, to first order and with the exact log-distance shift.
"""
import hashlib
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.colors as mc  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

from analysis import figstyle as fs  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _hex(c):
    return mc.to_hex(c).lower()


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ---------------------------------------------------------------------------------------------- palette
def test_every_scenario_has_its_own_colour_dash_and_marker():
    assert set(fs.SCENARIO) == set(fs.ORDER) == set(fs.MARKER)
    colours = [_hex(fs.SCENARIO[k]["color"]) for k in fs.ORDER]
    dashes = [str(fs.SCENARIO[k]["ls"]) for k in fs.ORDER]
    markers = [fs.MARKER[k] for k in fs.ORDER]
    assert len(set(colours)) == len(colours)            # colour alone tells them apart
    assert len(set(dashes)) == len(dashes)              # ... and so does the dash, in greyscale
    assert len(set(markers)) == len(markers)
    assert "^" not in markers                            # triangles are cell sites on the maps


def test_other_roles_never_reuse_a_scenario_colour():
    scen = {_hex(v["color"]) for v in fs.SCENARIO.values()}
    roles = {"event zone": fs.EVENT_ZONE["color"], "domain": fs.DOMAIN["color"], "d*_3": fs.REF_LINE["color"],
             "R": fs.RANGE_LINE["color"], "lie (Fig. 1)": fs.TEASER["lie"],
             "undetectable region (Fig. 1)": fs.TEASER["undetectable_edge"]}
    clash = {name: c for name, c in roles.items() if _hex(c) in scen}
    assert not clash, f"roles sharing a scenario colour: {clash}"


def test_consortium_only_series_never_borrow_an_operator_colour():
    ops = {_hex(fs.SCENARIO[k]["color"]) for k in ("A", "B", "C")}
    for table in (fs.METRIC, fs.SHADOW_K):
        looks = list(table.values())
        assert not {_hex(v["color"]) for v in looks} & ops
        assert len({(v["color"], str(v["ls"]), v["marker"]) for v in looks}) == len(looks)   # distinct in greyscale


def test_d3_star_and_R_look_the_same_in_every_figure():
    assert fs.TEASER["ok"] == fs.REF_LINE["color"]
    assert _hex(fs.TEASER["range_R"]) == _hex(fs.RANGE_LINE["color"])


# ---------------------------------------------------------------------------------------------- labels
@pytest.mark.parametrize("name,key", [("Consortium", "Consortium"), ("consortium", "Consortium"),
                                      ("Operator A", "A"), ("Operator B", "B"), ("C", "C")])
def test_scenario_label_decides_the_style(name, key):
    assert fs.scenario_key(name) == key
    assert fs.style(name)["color"] == fs.SCENARIO[key]["color"]


def test_unknown_scenario_fails_loudly():
    with pytest.raises(KeyError):
        fs.scenario_key("interlagos_op1")               # raw scenario id: must go through the alias first


# ---------------------------------------------------------------------------------------------- output
def test_save_is_deterministic(tmp_path):
    fs.use()
    hashes = []
    for k in range(2):
        fig, ax = plt.subplots(figsize=(3, 2))
        ax.plot([0, 1], [0, 1], **fs.style("A")); fs.tidy(ax)
        fs.save(fig, tmp_path / f"f{k}")
        plt.close(fig)
        assert (tmp_path / f"f{k}.png").exists()
        hashes.append(_sha(tmp_path / f"f{k}.pdf"))
    assert hashes[0] == hashes[1]


def _run(script, *args):
    return subprocess.run([sys.executable, str(ROOT / "analysis" / script), *args], cwd=ROOT,
                          capture_output=True, text=True)


def test_teaser_is_generated_and_deterministic(tmp_path):
    h = []
    for k in range(2):
        out = tmp_path / str(k)
        r = _run("teaser.py", "--out", str(out))
        assert r.returncode == 0, r.stderr               # the script's own asserts passed
        h.append(_sha(out / "fig_teaser.pdf"))
    assert h[0] == h[1]


def test_teaser_geometry_matches_the_caption():
    from analysis import teaser as t
    ra, rb = t.analyse(t.SITES_A), t.analyse(t.SITES_B)
    assert t.D3_STAR == pytest.approx(137.9, abs=0.1) and t.PD_MAX == pytest.approx(0.181, abs=1e-3)
    # (a) beyond d*_3, sigma_h > D, lie undetectable -- to first order and exactly
    assert ra["sigma_h"] > t.D_M and ra["inside"] and ra["pd_exact"] <= t.PD_MAX
    # (b) within d*_3, sigma_h <= D, lie outside -- to first order and exactly
    assert rb["sigma_h"] <= t.D_M and not rb["inside"] and rb["pd_exact"] > t.PD_MAX


def test_scenario_figures_demo_are_deterministic(tmp_path):
    h = {}
    for k in range(2):
        out = tmp_path / str(k)
        r = _run("fig_scenario.py", "--demo", "--out", str(out))
        assert r.returncode == 0, r.stderr
        for name in ("fig_scenario_demo.pdf", "fig_scenario_operators_demo.pdf"):
            h.setdefault(name, []).append(_sha(out / name))
    assert all(a == b for a, b in h.values())
