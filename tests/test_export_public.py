"""Export to the public repository: allowlist + safety scan (tools/export_public.py). Names below are invented."""
import json
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "export_public.py"
NAME = "ACME" + "FONE"                         # invented operator name, built at runtime
OLD = "cs-rid-" + "spoof" + "ing"              # old repository name, built at runtime


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _private_repo(tmp_path, leak=False):
    r = tmp_path / "private"
    (r / "experiments/configs/local").mkdir(parents=True)
    (r / "src").mkdir()
    (r / "data/external/flights/raw").mkdir(parents=True)
    (r / "tools").mkdir()
    cfg = {"presentation_file": "experiments/configs/local/presentation.yaml",
           "stage_a": {"paths": {"flights_raw": "data/external/flights/raw/raw.csv"}, "leak_test_ignore": ["encrypted"]}}
    (r / "experiments/configs/reference.yaml").write_text(yaml.safe_dump(cfg))
    (r / "experiments/configs/local/presentation.yaml").write_text(
        yaml.safe_dump({"presentation": {"operator_alias": {NAME: "A"}}}))
    (r / "data/external/flights/raw/raw.csv").write_text("flight_id,lat\nSERIALXYZ123,1\nencrypted,2\n")
    (r / "src/model.py").write_text("x = 1  # encrypted payloads are ignored\n" + (f"# {NAME}\n" if leak else ""))
    (r / "src/notes.txt").write_text(("see SERIALXYZ123\n" if leak else "clean\n") + (f"{OLD}\n" if leak else ""))
    (r / "src/data.parquet").write_bytes(b"PAR1")
    (r / "tools/MANIFEST-PUBLIC.txt").write_text(
        "include src/*\nexclude src/data.parquet\ninclude experiments/configs/reference.yaml\n")
    (r / ".gitignore").write_text("experiments/configs/local/\ndata/external/flights/raw/\n")
    _git(r, "init", "-q")
    _git(r, "add", "-A")
    _git(r, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return r


def _run(root, dest, *extra):
    return subprocess.run([sys.executable, str(TOOL), "--root", str(root), "--manifest", "tools/MANIFEST-PUBLIC.txt",
                           "--dest", str(dest), *extra], capture_output=True, text=True)


def test_clean_export_copies_only_allowlisted_tracked_files(tmp_path):
    root = _private_repo(tmp_path)
    r = _run(root, tmp_path / "public")
    assert r.returncode == 0, r.stdout + r.stderr
    got = sorted(p.relative_to(tmp_path / "public").as_posix() for p in (tmp_path / "public").rglob("*") if p.is_file())
    assert got == ["experiments/configs/reference.yaml", "src/model.py", "src/notes.txt"]
    assert not (tmp_path / "public/experiments/configs/local").exists()      # private mapping never exported


def test_published_test_depending_on_private_tool_is_reported(tmp_path):
    root = _private_repo(tmp_path)
    (root / "tools/helper.py").write_text("print('private')\n")
    (root / "src/test_helper.py").write_text("TOOL = REPO / 'tools' / 'helper.py'\n")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "helper")
    # the published test (copied to tests/) names tools/helper.py, which is tracked but not published
    (root / "tools/MANIFEST-PUBLIC.txt").write_text(
        "include src/model.py\ncopy src/test_helper.py -> tests/test_helper.py\n")
    r = _run(root, tmp_path / "public")
    assert r.returncode == 1
    rep = json.loads((tmp_path / "public-EXPORT_REPORT.json").read_text())
    assert any(f["file"] == "tests/test_helper.py" and "tools/helper.py" in f["issue"] for f in rep["findings"])
    assert not (tmp_path / "public").exists()


def test_leaks_are_reported_and_nothing_is_copied(tmp_path):
    root = _private_repo(tmp_path, leak=True)
    r = _run(root, tmp_path / "public")
    assert r.returncode == 1
    rep = json.loads((tmp_path / "public-EXPORT_REPORT.json").read_text())
    issues = {(f["file"], f["issue"].split(" (")[0]) for f in rep["findings"]}
    assert ("src/model.py", "forbidden term") in issues
    assert any(f["file"] == "src/notes.txt" and "raw flight identifier" in f["issue"] for f in rep["findings"])
    assert not (tmp_path / "public").exists()
    assert "SERIALXYZ123" not in r.stdout                                    # identifiers are never printed
