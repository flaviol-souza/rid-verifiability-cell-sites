"""Block B: the 8 keys that numbers_derived.tex holds today, as a pure function for experiments/run_freeze.py.

Rules (each one is the definition used in the paper's text):
  desc_total_flight_time_h          desc_total_flight_time_s / 3600, 1 dp
  inv_n_sites                       distinct (lat, lon) positions in the ANATEL extract (all generations, three
                                    operators); asserts that no two operators share a position (claimed in Sec. 4)
  mech_R1000_v3_lo_mean_consortium  mean over the 89 sessions of v3_lower (R = 1 km, sites beyond r_max not simulated)
  mech_R1000_v3_hi_mean_<sc>        mean over sessions of v3_upper (every site of the extract beyond r_max treated as
                                    heard), sc in consortium, opA, opB
  mech_R1000_v3_hi_max_opC          max over sessions of v3_upper for operator C
  mech_R1000_max_d3_verifiable_all  max of d3_median_m over all sessions of all four scenarios with v3_upper >= 0.5
Inputs are the F3 spike outputs f3_sessions_<scenario>.csv (columns v3_lower, v3_upper, d3_median_m; one row per
session). op_map maps the file's scenario label to the paper's label, so that no operator name reaches the macros.
"""
import csv, os, statistics as st

def b_keys(total_flight_time_s, anatel_csv, f3_dir, op_map, n_sessions=89):
    out = {"desc_total_flight_time_h": round(total_flight_time_s / 3600, 1)}
    with open(anatel_csv, newline="", encoding="utf-8-sig") as f:
        head = f.readline(); f.seek(0)
        rows = list(csv.DictReader(f, delimiter=";" if head.count(";") > head.count(",") else ","))
    pos = {(r["Latitude decimal"], r["Longitude decimal"]) for r in rows}
    pos_op = {(r["Latitude decimal"], r["Longitude decimal"], r["Empresa Estação"]) for r in rows}
    assert len(pos) == len(pos_op), "two operators share a position: Section 4 says they do not"
    out["inv_n_sites"] = len(pos)
    sess = {}
    for label, paper in op_map.items():
        with open(os.path.join(f3_dir, f"f3_sessions_{label}.csv"), newline="") as f:
            sess[paper] = [{k: float(r[k]) for k in ("v3_lower", "v3_upper", "d3_median_m")} for r in csv.DictReader(f)]
        assert len(sess[paper]) == n_sessions, (label, len(sess[paper]))
    out["mech_R1000_v3_lo_mean_consortium"] = round(st.mean(r["v3_lower"] for r in sess["consortium"]), 2)
    for sc in ("consortium", "opA", "opB"):
        out[f"mech_R1000_v3_hi_mean_{sc}"] = round(st.mean(r["v3_upper"] for r in sess[sc]), 2)
    out["mech_R1000_v3_hi_max_opC"] = round(max(r["v3_upper"] for r in sess["opC"]), 2)
    out["mech_R1000_max_d3_verifiable_all"] = round(max(r["d3_median_m"] for s in sess.values() for r in s
                                                       if r["v3_upper"] >= 0.5))
    return out

if __name__ == "__main__":   # self-test: python3 -I b_keys.py TOTAL_S ANATEL_CSV F3_DIR
    import sys
    op = {"consortium": "consortium", "VIVO": "opA", "CLARO": "opB", "TIM": "opC"}
    print(b_keys(float(sys.argv[1]), sys.argv[2], sys.argv[3], op))
