"""Gate 2: compare the checker with the Blue Book UB resistance tables. Exit code 1 if any check fails.
Usage: python scripts/gate2_bluebook.py [data-dir]   (default data/raw; needs the three Blue Book workbooks there)"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ub_rl.catalogue import parse_workbook, sha256_file  # noqa: E402
from ub_rl import bluebook as bb  # noqa: E402

d = sys.argv[1] if len(sys.argv) > 1 else "data/raw"
props = os.path.join(d, "UB-secpropsdimsprops-EC3UKNA-UK-10-16-2026.xlsx")
bend_p = os.path.join(d, "UB-bending-S355-EC3UKNA-UK-10-20-2026.xlsx")
bear_p = os.path.join(d, "UB-webbearingbuckling-S355-EC3UKNA-UK-10-20-2026.xlsx")
cat, _ = parse_workbook(props)
bend, bear = bb.parse_bending(bend_p), bb.parse_bearing(bear_p)
print("SHA-256 bending", sha256_file(bend_p)); print("SHA-256 bearing", sha256_file(bear_p))
ok = True
r = bb.compare_class_mc(cat, bend)
print(f"class mismatches {len(r['class_mismatch'])}; Iy mismatches {len(r['Iy_mismatch'])}; Mc,y,Rd outside rounding {len(r['Mc_outside'])} of {r['n']} (max rel dev {100*r['Mc_max_rel_dev']:.2f}%)")
ok &= not (r["class_mismatch"] or r["Iy_mismatch"] or r["Mc_outside"])
r = bb.compare_vc(cat, bear)
print(f"Vc,Rd outside rounding {len(r['Vc_outside'])} of {r['n']} (max rel dev {100*r['Vc_max_rel_dev']:.2f}%)")
ok &= not r["Vc_outside"]
r = bb.compare_bearing(cat, bear)
print(f"FRd(c=0), ss <= hw: outside rounding {len(r['strict_outside'])} of {r['strict_n']}; ss > hw (checker limits ss to hw): "
      f"{r['capped_n']} values, checker above table in {len(r['capped_unconservative'])}; min hw {r['min_hw']:.1f} mm")
ok &= not (r["strict_outside"] or r["capped_unconservative"])
r = bb.compare_mb(cat, bend)
print(f"Mb,Rd outside rounding {len(r['outside'])} of {r['n']}")
for x in r["outside"][:10]: print("  ", x)
ok &= not r["outside"]
print("GATE 2 BLUE BOOK COMPARISON:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
