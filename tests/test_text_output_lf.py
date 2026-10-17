"""Ensure Stage A text writers request LF explicitly."""
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_stage_a_text_writers_force_lf() -> None:
    """Production text writers contain no implicit platform newline mode."""
    files = [
        ROOT / "tools" / "make_roi.py",
        ROOT / "tools" / "check_terrain.py",
        ROOT / "src" / "drs" / "data" / "stage_a.py",
        ROOT / "experiments" / "run_stage_a.py",
    ]
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "\r" not in text
    assert 'newline="\\n"' in (ROOT / "tools" / "make_roi.py").read_text(encoding="utf-8")
    assert 'newline="\\n"' in (ROOT / "src" / "drs" / "data" / "stage_a.py").read_text(encoding="utf-8")
    runner = (ROOT / "experiments" / "run_stage_a.py").read_text(encoding="utf-8")
    assert runner.count('newline="\\n"') == 2
