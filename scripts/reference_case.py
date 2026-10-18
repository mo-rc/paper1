"""Print the checker result for the reference case (9 m, 56.7675 kN/m) for sets C and C+.
Usage: python scripts/reference_case.py [path-to-xlsx]"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ub_rl.catalogue import parse_workbook  # noqa: E402
from ub_rl.checker import Checker  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
XLSX = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "raw", "UB-secpropsdimsprops-EC3UKNA-UK-10-16-2026.xlsx")
L, W = 9.0, 56.7675

cat, _ = parse_workbook(XLSX)
for label, inc in (("C", False), ("C+", True)):
    S = cat.mass_ordered(inc)
    K = Checker(S)
    i = K.lightest_feasible(L, W)
    print(f"== {label} ({len(S)} sections): lightest feasible = {S.names[i]}")
    for j in (i - 1, i, i + 1):
        r = K.check(L, W, j)
        print(f"  {r.name:12s} {r.mass:6.1f} kg/m feasible={r.feasible!s:5s} governing={r.governing:13s} "
              f"bend {r.u_bending:.3f} shear {r.u_shear:.3f} int {r.u_bending_shear:.3f} brg {r.u_web_bearing:.3f} defl {r.u_deflection:.3f}")
