"""How often does the lightest feasible section change if full-span UDL factors (C1 = 1.127, kc = 0.94) are used for
intermediate restraints instead of the conservative uniform-moment factors (C1 = 1, kc = 1)?

300 contexts per restraint ratio (0.25 and 0.5), L in [9, 15] m, factored superimposed UDL in [56, 100] kN/m,
numpy default_rng(seed 0). Prints the counts quoted in docs/verification_record.md. Exploratory, not part of the study."""
import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))  # use the repository src/ (run from the repository root)
import sys
from dataclasses import replace

import numpy as np

from ub_rl.catalogue import parse_workbook
from ub_rl.checker import Checker
from ub_rl.config import CheckerConfig

path = sys.argv[1] if len(sys.argv) > 1 else "data/raw/UB-secpropsdimsprops-EC3UKNA-UK-10-16-2026.xlsx"
cat, _ = parse_workbook(path)
C = cat.mass_ordered(False)
rng = np.random.default_rng(0)
diff = n = 0
for ratio in (0.25, 0.5):
    cons = Checker(C, replace(CheckerConfig(), restraint_ratio=ratio))
    udl = Checker(C, replace(CheckerConfig(), restraint_ratio=ratio, ltb_segment_C1=1.127, ltb_segment_kc=0.94))
    for _ in range(300):
        L, w = rng.uniform(9, 15), rng.uniform(56, 100)
        n += 1
        diff += cons.lightest_feasible(L, w) != udl.lightest_feasible(L, w)
print(f"optimum differs in {diff} of {n} contexts ({100 * diff / n:.0f} %)")
