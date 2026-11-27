"""Build the public repository from the private one: allowlist copy + safety scan. Never runs git push.

  python tools/export_public.py --manifest tools/MANIFEST-PUBLIC.txt --dest ../cs-rid-hearing [--dry-run]

Manifest lines (blank lines and '#' comments ignored):
  include <glob>          git-tracked files to copy (path kept)
  exclude <glob>          removes matches from the includes
  copy <src> -> <dest>    one file copied from anywhere in the private tree (e.g. regenerated figures, freeze)
  allow-csv <glob>        .csv/.png paths (destination) that may be published

Findings (any finding -> exit 1, nothing is considered ready):
  * blocked file types (.parquet .pkl .tif .zip .npz .db .env ...) or a .csv/.png not allowed by allow-csv
  * files larger than --max-mb
  * raw operator names (from the private alias mapping, >= 3 letters) and extra terms from --deny-file
  * strings that must never be public (rejected-submission citation, old repository name, private keys, key values,
    the operator mapping block)
  * any raw flight identifier read from the raw flight file (values only compared, never printed)
  * a published test that names a tracked .py file which is not published (it would fail in the public repo)
PDFs are checked through `pdftotext` when it is available; otherwise they are reported as unchecked findings.
"""
import argparse
import fnmatch
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BLOCKED_EXT = {".parquet", ".pkl", ".pickle", ".tif", ".tiff", ".zip", ".gz", ".npz", ".npy", ".h5", ".db",
               ".sqlite", ".env", ".key", ".pem", ".xlsx"}
ALWAYS_DENY = [r"SBRC\s*2026", r"souza2026", r"Al[eé]m do Remote ID", r"cs-rid-spoofing",
               r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"DSV2_HMAC_KEY\s*[:=]\s*['\"]?[0-9A-Fa-f]{16,}",
               r"operator_alias\s*:\s*\{?\s*\w+\s*:"]                   # a mapping block, not the code that reads it


def parse_manifest(path: Path):
    inc, exc, copies, allow = [], [], [], []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        kind, _, rest = line.partition(" ")
        rest = rest.strip()
        if kind == "include":
            inc.append(rest)
        elif kind == "exclude":
            exc.append(rest)
        elif kind == "allow-csv":
            allow.append(rest)
        elif kind == "copy" and "->" in rest:
            src, dst = (x.strip() for x in rest.split("->", 1))
            copies.append((src, dst))
        else:
            raise SystemExit(f"manifest line {n}: cannot parse '{line}'")
    return inc, exc, copies, allow


def tracked_files(root: Path) -> list:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True).stdout
    return [p.decode() for p in out.split(b"\0") if p]


def match(path: str, globs: list) -> bool:
    return any(fnmatch.fnmatch(path, g) for g in globs)


def text_of(path: Path):
    if path.suffix.lower() == ".pdf":
        if shutil.which("pdftotext") is None:
            return None
        return subprocess.run(["pdftotext", str(path), "-"], capture_output=True).stdout.decode("utf-8", "ignore")
    return path.read_bytes().decode("utf-8", "ignore")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="tools/MANIFEST-PUBLIC.txt")
    ap.add_argument("--dest", required=True)
    ap.add_argument("--config", default="experiments/configs/reference.yaml")
    ap.add_argument("--deny-file", help="private file with extra terms, one regex per line (never exported)")
    ap.add_argument("--max-mb", type=float, default=5.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--root", help="private repository root (default: the repository containing this tool)")
    a = ap.parse_args()
    root = Path(a.root).resolve() if a.root else ROOT

    cfg = yaml.safe_load((root / a.config).read_text())
    from analysis.alias import load_alias
    alias = load_alias(cfg, root)
    if not alias:
        raise SystemExit("no operator mapping found (presentation_file or presentation block): cannot check names")
    deny = [rf"(?<![A-Za-z]){re.escape(r)}(?![A-Za-z])" for r in alias if len(r) >= 3] + ALWAYS_DENY
    if a.deny_file:
        deny += [l.strip() for l in Path(a.deny_file).read_text(encoding="utf-8").splitlines() if l.strip()]
    deny_re = re.compile("|".join(f"(?:{d})" for d in deny), re.I)

    raw_ids = set()
    raw = root / cfg["stage_a"]["paths"]["flights_raw"]
    if raw.exists():
        import pandas as pd
        ignore = set(cfg["stage_a"].get("leak_test_ignore", []))
        raw_ids = {s for s in pd.read_csv(raw, dtype={"flight_id": str})["flight_id"].dropna().unique()} - ignore

    inc, exc, copies, allow = parse_manifest(root / a.manifest)
    tracked = tracked_files(root)
    plan = [(p, p) for p in tracked if match(p, inc) and not match(p, exc)]
    left_out = sorted(p for p in tracked if (p, p) not in plan)
    plan += copies
    dest = Path(a.dest).resolve()
    if dest == root or root in dest.parents:
        raise SystemExit("--dest must be outside the private repository")
    findings, files = [], []
    for src, dst in plan:
        s = root / src
        if not s.is_file():
            findings.append({"file": dst, "issue": f"source missing: {src}"})
            continue
        ext = s.suffix.lower()
        if ext in BLOCKED_EXT:
            findings.append({"file": dst, "issue": f"blocked file type {ext}"})
            continue
        if ext in {".csv", ".png", ".jpg", ".jpeg", ".gif"} and not match(dst, allow):
            findings.append({"file": dst, "issue": f"{ext} not allowed by allow-csv"})
            continue
        if s.stat().st_size > a.max_mb * 1e6:
            findings.append({"file": dst, "issue": f"larger than {a.max_mb} MB"})
            continue
        if ext == ".gif":   # binary image, allow-listed by name and checked by eye; a text scan only gives false hits
            files.append({"path": dst, "sha256": hashlib.sha256(s.read_bytes()).hexdigest(), "bytes": s.stat().st_size})
            continue
        txt = text_of(s)
        if txt is None:
            findings.append({"file": dst, "issue": "PDF not checked (pdftotext missing)"})
        else:
            m = deny_re.search(txt)
            if m:
                findings.append({"file": dst, "issue": "forbidden term", "line": txt[:m.start()].count("\n") + 1})
        if raw_ids:
            data = s.read_bytes()
            n_hit = sum(1 for r in raw_ids if r.encode() in data)
            if n_hit:
                findings.append({"file": dst, "issue": f"{n_hit} raw flight identifier(s) found"})
        files.append({"path": dst, "sha256": hashlib.sha256(s.read_bytes()).hexdigest(), "bytes": s.stat().st_size})
    report = {"files": sorted(files, key=lambda f: f["path"]), "findings": findings,
              "raw_identifiers_checked": len(raw_ids), "deny_terms": len(deny), "tracked_but_not_exported": left_out}
    # A published test must not depend on a script that stays private (it would fail in the public repo).
    planned_dst = {d for _, d in plan}
    tracked_by_name = {}
    for p in tracked:
        tracked_by_name.setdefault(Path(p).name, []).append(p)
    for src, dst in plan:
        if not (dst.startswith("tests/") and dst.endswith(".py")) or not (root / src).is_file():
            continue
        names = set(re.findall(r"""["']([\w.-]+\.py)["']""", (root / src).read_text(encoding="utf-8", errors="ignore")))
        for n in sorted(names - {Path(dst).name}):
            private = [p for p in tracked_by_name.get(n, []) if p not in planned_dst]
            if private and not any(Path(d).name == n for d in planned_dst):
                findings.append({"file": dst, "issue": f"test depends on non-exported file: {private[0]}"})
    report["findings"] = findings
    if not findings and not a.dry_run:
        if dest.exists() and any(dest.iterdir()):
            raise SystemExit(f"{dest} exists and is not empty")
        for src, dst in plan:
            t = dest / dst
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / src, t)
    rep = dest.parent / f"{dest.name}-EXPORT_REPORT.json"
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"{len(files)} files planned, {len(left_out)} tracked files left out, {len(findings)} finding(s); report: {rep}")
    for f in findings:
        print("  FINDING", f)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
