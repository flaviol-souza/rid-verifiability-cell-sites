"""Cross-check results/freeze/numbers.csv against values verified independently during the review (expected.json).

Usage: python check_freeze.py --numbers results/freeze/numbers.csv --expected expected.json
Prints one line per checked key and exits 1 on any mismatch or missing key. Read-only.
"""
import argparse
import json
import sys

import pandas as pd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--numbers", required=True)
    ap.add_argument("--expected", required=True)
    a = ap.parse_args()
    n = pd.read_csv(a.numbers, dtype={"value": str}).set_index("key")
    exp = json.load(open(a.expected, encoding="utf-8"))
    bad = 0
    for key, (val, tol, src) in exp.items():
        if key not in n.index:
            print(f"MISSING  {key}  (expected {val}; source of expectation: {src})")
            bad += 1
            continue
        got = n.at[key, "value"]
        if tol is None:
            ok = str(got).strip() == str(val)
        else:
            try:
                ok = abs(float(got) - float(val)) <= float(tol)
            except ValueError:
                ok = False
        print(f"{'OK      ' if ok else 'MISMATCH'} {key} = {got}  (expected {val} ± {tol}; {src})")
        bad += 0 if ok else 1
    extra = sorted(set(n.index) - set(exp))
    print(f"\n{len(exp) - bad}/{len(exp)} checked keys match; {len(extra)} keys not cross-checked: {', '.join(extra)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
