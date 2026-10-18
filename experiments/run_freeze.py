"""Freeze every number the paper quotes, with its source, so no number is ever typed into the text.

Reads the result files (never recomputes), writes:
  numbers.csv          key, value, formatted, source file, selector
  numbers.tex          \\ds{key} macros for LaTeX (an undefined key prints a visible ??key)
  results_freeze.md    one table per section, plus the commit hash and the sha256 of every input file

Usage:
  python experiments/run_freeze.py --blockO results/stage_b/blockO \\
      --blockS group1=results/stage_b/S_exclude_group1 --blockS anchor=... \\
      --mechanism results/stage_b/mechanism --map results/stage_b/map --out results/freeze
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SECTIONS = ["Observability", "Verifiability", "Serial heterogeneity", "H1 cooperation", "H2 gap", "H2 robustness",
            "H3 ranking", "Mechanism (exploratory)", "Inventory and truncation"]


class Freezer:
    def __init__(self, root: Path):
        self.root, self.rows, self.inputs = root, [], {}

    def _src(self, path: Path) -> str:
        rel = str(path.relative_to(self.root))
        if rel not in self.inputs:
            self.inputs[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        return rel

    def add(self, section, key, value, path, selector, kind="frac"):
        if value is None or (isinstance(value, float) and pd.isna(value)):
            raise KeyError(f"missing value for {key} ({selector}) in {path}")
        if kind == "frac":
            fmt = f"{float(value):.2f}"
        elif kind == "rho":
            fmt = f"{float(value):.2f}"
        elif kind == "m":
            fmt = f"{float(value):,.0f}"
        elif kind == "int":
            fmt = f"{int(value)}"
        elif kind == "pct":
            fmt = f"{100 * float(value):.0f}\\%"
        else:
            fmt = str(value)
        self.rows.append({"section": section, "key": key, "value": value, "formatted": fmt,
                          "source": self._src(path), "selector": selector})
        if kind == "frac":                                   # every fraction also as a rounded percentage
            self.rows.append({"section": section, "key": key + "_pct", "value": value,
                              "formatted": f"{100 * float(value):.0f}\\%", "source": self._src(path),
                              "selector": selector + " [x100]"})


def _one(df, path, **sel):
    m = df
    for k, v in sel.items():
        m = m[m[k] == v]
    if len(m) != 1:
        raise KeyError(f"{path}: expected 1 row for {sel}, got {len(m)}")
    return m.iloc[0]


def _sel(**sel):
    return ", ".join(f"{k}={v}" for k, v in sel.items())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="experiments/configs/reference.yaml")
    ap.add_argument("--root", default=".")
    ap.add_argument("--blockO", required=True)
    ap.add_argument("--blockS", action="append", default=[], help="label=dir, repeatable")
    ap.add_argument("--mechanism", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--family", default="c1_generic")
    ap.add_argument("--map-scenario", action="append", default=[], help="scenario=map_dir, repeatable")
    ap.add_argument("--allow-raw-names", action="store_true", help="internal use only: keep operator names in keys")
    a = ap.parse_args()
    root = Path(a.root).resolve()
    cfg = yaml.safe_load((root / a.config).read_text())
    b = cfg["stage_b"]
    from analysis.alias import check, key as akey, load_alias
    alias = load_alias(cfg, root)
    Rref, D = float(b["range_ref_m"]), int(b["verif_scale_ref_m"])
    fz = Freezer(root)
    fam = a.family
    blk = root / a.blockO

    # --- summary.csv: observability, verifiability, serial weighting
    sp = blk / "summary" / "summary.csv"
    s = pd.read_csv(sp)
    ops = sorted(x for x in s.loc[s["family"] == fam, "scenario"].unique() if x != "consortium")
    main_ranges = sorted(float(r) for r in s.loc[s["family"] == fam, "range_m"].unique() if r <= Rref)   # quoted ranges
    scen = ["consortium"] + ops
    if not alias and not a.allow_raw_names:
        raise SystemExit("operators must be de-identified: set presentation.operator_alias in the config "
                         "(or pass --allow-raw-names for internal use)")
    check(alias, ops)
    for R in main_ranges:
        r = int(R)
        for sc in scen:
            for k in (1, 3):
                sel = dict(family=fam, scenario=sc, range_m=R, metric=f"observable_k{k}")
                row = _one(s, sp, **sel)
                fz.add("Observability", f"obs_k{k}_{akey(sc, alias)}_R{r}", row["mean"], sp, _sel(**sel))
        for sc in scen:
            for lvl in (3, 4):
                sel = dict(family=fam, scenario=sc, range_m=R, metric=f"V{lvl}_D{D}")
                row = _one(s, sp, **sel)
                fz.add("Verifiability", f"V{lvl}_D{D}_{akey(sc, alias)}_R{r}", row["mean"], sp, _sel(**sel))
                if sc == "consortium":
                    fz.add("Verifiability", f"V{lvl}_D{D}_{sc}_R{r}_cilo", row["ci_lo"], sp, _sel(**sel) + " [ci_lo]")
                    fz.add("Verifiability", f"V{lvl}_D{D}_{sc}_R{r}_cihi", row["ci_hi"], sp, _sel(**sel) + " [ci_hi]")
                    fz.add("Serial heterogeneity", f"V{lvl}_D{D}_{sc}_R{r}_serialw", row["serial_weighted_mean"], sp,
                           _sel(**sel) + " [serial_weighted_mean]")
    row = _one(s, sp, family=fam, scenario="consortium", range_m=Rref, metric=f"V3_D{D}")
    fz.add("Serial heterogeneity", "top_serial_session_share", row["top_serial_session_share"], sp,
           "any row [top_serial_session_share]", "pct")
    fz.add("Serial heterogeneity", "n_sessions", row["n_sessions"], sp, "any row [n_sessions]", "int")
    fz.add("Serial heterogeneity", "n_serials", row["n_serials"], sp, "any row [n_serials]", "int")
    for op in ops:
        t = s[(s["family"] == fam) & (s["scenario"] == op) & (s["metric"] == f"V3_D{D}")]
        fz.add("Verifiability", f"V3_D{D}_{akey(op, alias)}_maxR", t["mean"].max(), sp, f"max over range_m of {op} V3_D{D}")

    # --- hypotheses
    hp = blk / "hypotheses"
    h1 = pd.read_csv(hp / "h1.csv")
    for R in main_ranges:
        for k in (1, 3):
            sel = dict(family=fam, range_m=R, k=k)
            row = _one(h1, hp / "h1.csv", **sel)
            fz.add("H1 cooperation", f"h1_k{k}_R{int(R)}", row["mean_reduction"], hp / "h1.csv", _sel(**sel))
            fz.add("H1 cooperation", f"h1_k{k}_R{int(R)}_reject", "yes" if row["reject_h0"] else "no",
                   hp / "h1.csv", _sel(**sel) + " [reject_h0]", "text")
    h2 = pd.read_csv(hp / "h2.csv")
    for lvl in ("V3", "V4"):
        sel = dict(family=fam, level=lvl)
        row = _one(h2, hp / "h2.csv", **sel)
        for col in ("mean_gap", "ci_lo", "ci_hi"):
            fz.add("H2 gap", f"h2_{lvl}_{col}", row[col], hp / "h2.csv", _sel(**sel) + f" [{col}]")
        fz.add("H2 gap", f"h2_{lvl}_reject", "yes" if row["reject_h0"] else "no", hp / "h2.csv",
               _sel(**sel) + " [reject_h0]", "text")
    for spec in a.blockS:
        label, d = spec.split("=", 1)
        p = root / d / "hypotheses" / "h2.csv"
        row = _one(pd.read_csv(p), p, level="V3")
        fz.add("H2 robustness", f"h2S_{label}_gap", row["mean_gap"], p, "level=V3 [mean_gap]")
        fz.add("H2 robustness", f"h2S_{label}_reject", "yes" if row["reject_h0"] else "no", p, "level=V3 [reject_h0]",
               "text")
    h3 = pd.read_csv(hp / "h3.csv")
    h3m = h3[(h3["family"] == fam) & (h3["range_m"].isin(main_ranges))]
    fz.add("H3 ranking", "h3_holds", int(h3m["holds"].sum()), hp / "h3.csv", f"range_m in {main_ranges} [sum holds]", "int")
    fz.add("H3 ranking", "h3_cells", len(h3m), hp / "h3.csv", f"range_m in {main_ranges} [count]", "int")
    tr = pd.read_csv(hp / "truncated_cells.csv")
    trunc = sorted(tr.loc[(tr["family"] == fam) & tr["truncated"], "range_m"].astype(int).tolist())
    fz.add("Inventory and truncation", "truncated_ranges", ", ".join(map(str, trunc)), hp / "truncated_cells.csv",
           "truncated == True", "text")

    # --- mechanism
    mp = root / a.mechanism / "mechanism_summary.csv"
    m = pd.read_csv(mp)
    for sc in [x for x in m["scenario"] if pd.notna(_one(m, mp, scenario=x)["spearman_rho"])]:
        row = _one(m, mp, scenario=sc)
        k_ = akey(sc, alias)
        fz.add("Mechanism (exploratory)", f"mech_rho_d3_{k_}", row["spearman_rho"], mp, f"scenario={sc} [spearman_rho]", "rho")
        fz.add("Mechanism (exploratory)", f"mech_rho_geo_{k_}", row[f"spearman_rho_V3_D{D}_vs_geo"], mp,
               f"scenario={sc} [spearman_rho_V3_D{D}_vs_geo]", "rho")
        fz.add("Mechanism (exploratory)", f"mech_mae_geo_{k_}", row[f"mean_abs_V3_D{D}_minus_geo"], mp,
               f"scenario={sc} [mean_abs_V3_D{D}_minus_geo]")
    sp2 = root / a.mechanism / "mechanism_sessions.csv"
    if sp2.exists():
        ms = pd.read_csv(sp2)
        for sc in ["consortium"] + ops:
            g = ms[ms["scenario"] == sc]
            if len(g):
                dlt = g[f"V3_D{D}"] - g[f"V3_D{D}_geo"]
                fz.add("Mechanism (exploratory)", f"mech_sim_above_geo_{akey(sc, alias)}", int((dlt > 0.2).sum()), sp2,
                       f"scenario={sc}: sessions with V3 - V3_geo > 0.2", "int")
                fz.add("Mechanism (exploratory)", f"mech_geo_above_sim_{akey(sc, alias)}", int((dlt < -0.2).sum()), sp2,
                       f"scenario={sc}: sessions with V3_geo - V3 > 0.2", "int")
    row = _one(m, mp, scenario="consortium")
    fz.add("Mechanism (exploratory)", "mech_close_unverifiable", row["n_close_but_unverifiable"], mp,
           "scenario=consortium [n_close_but_unverifiable]", "int")
    fz.add("Mechanism (exploratory)", "mech_dlimit3", row["d_limit_3sites_m"], mp, "d_limit_3sites_m", "m")

    # --- maps: share of flight time in cells that are (almost) never verifiable
    for spec in a.map_scenario:
        sc, d = spec.split("=", 1)
        cp = root / d / "cells.csv"
        c = pd.read_csv(cp)
        col = f"frac_V3_D{D}"
        fz.add("Mechanism (exploratory)", f"map_blind_share_{akey(sc, alias)}",
               float(c.loc[c[col] < 0.1, "time_s"].sum() / c["time_s"].sum()), cp,
               f"time share in cells with {col} < 0.1", "pct")
        fz.add("Mechanism (exploratory)", f"map_v3_pooled_{akey(sc, alias)}",
               float((c[col] * c["time_s"]).sum() / c["time_s"].sum()), cp, f"time-weighted {col} (pooled over sessions)")

    # --- inventory margin
    jp = root / a.map / "inventory_margin.json"
    j = json.loads(jp.read_text())
    for k, kind in [("min_sample_distance_to_inventory_edge_m", "m"), ("max_untruncated_range_at_configured_r_max_m", "m"),
                    ("max_untruncated_range_if_r_max_raised_m", "m"), ("configured_r_max_m", "m")]:
        fz.add("Inventory and truncation", f"inv_{k}", j[k], jp, k, kind)
    fz.add("Inventory and truncation", "inv_basis", j["basis"], jp, "basis", "text")

    # --- write
    out = root / a.out
    out.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(fz.rows)
    if df["key"].duplicated().any():
        raise RuntimeError(f"duplicate keys: {df.loc[df['key'].duplicated(), 'key'].tolist()}")
    df.to_csv(out / "numbers.csv", index=False, lineterminator="\n")
    tex = ["% generated by experiments/run_freeze.py -- do not edit",
           "\\makeatletter",
           "\\newcommand{\\ds}[1]{\\ifcsname ds@#1\\endcsname\\csname ds@#1\\endcsname"
           "\\else\\@latex@warning{ds: undefined key \\detokenize{#1}}\\textbf{??\\detokenize{#1}}\\fi}"]
    for r in fz.rows:
        tex.append(f"\\expandafter\\def\\csname ds@{r['key']}\\endcsname{{{r['formatted']}}}")
    tex.append("\\makeatother")
    (out / "numbers.tex").write_bytes(("\n".join(tex) + "\n").encode())
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
    except OSError:
        commit = ""
    def write_md(frame, inputs, path):
        md = ["# Results freeze", "", f"Commit: `{commit or 'unknown'}`. Generated by `experiments/run_freeze.py`; "
              "do not edit by hand. In LaTeX: `\\input{numbers.tex}` and `\\ds{key}`.", ""]
        for sec in SECTIONS:
            part = frame[frame["section"] == sec]
            if part.empty:
                continue
            md += [f"## {sec}", "", "| Key | Value | Source | Selector |", "|---|---|---|---|"]
            md += [f"| `{r.key}` | {r.formatted.replace(chr(92) + '%', '%')} | `{r.source}` | {r.selector} |"
                   for r in part.itertuples()]
            md.append("")
        md += ["## Input files", "", "| File | sha256 |", "|---|---|"]
        md += [f"| `{f}` | `{h}` |" for f, h in sorted(inputs.items())]
        path.write_bytes(("\n".join(md) + "\n").encode())

    write_md(df, fz.inputs, out / "results_freeze.md")            # internal: real selectors and paths
    if alias:                                                      # public: operator names replaced everywhere
        from analysis.alias import sanitize
        pub = df.assign(source=df["source"].map(lambda t: sanitize(t, alias, "path")),
                        selector=df["selector"].map(lambda t: sanitize(t, alias, "label")))
        pub.drop(columns=["value"]).to_csv(out / "numbers_public.csv", index=False, lineterminator="\n")
        write_md(pub, {sanitize(f, alias, "path"): h for f, h in fz.inputs.items()}, out / "results_freeze_public.md")
        import re
        names = [r for r in alias if len(r) >= 3]                  # 1-2 letter test names cannot be checked by text
        pat = re.compile("|".join(rf"(?<![A-Za-z]){re.escape(r)}(?![A-Za-z])" for r in names), re.I) if names else None
        for f in ("numbers.tex", "numbers_public.csv", "results_freeze_public.md"):
            if pat is not None and pat.search((out / f).read_text(encoding="utf-8")):
                raise RuntimeError(f"operator name left in public output {f}")
    print(f"{len(df)} numbers frozen -> {out.relative_to(root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
