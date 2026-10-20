"""Two independent implementations of the non-LTB checks agree (Gate 2 evidence, part 2). See tests/reference_checks.py."""
from dataclasses import replace

import numpy as np
import pytest

from ub_rl.checker import Checker
from ub_rl.config import CheckerConfig, PHI_REF

import reference_checks as R

CONTEXTS = [(6, 40), (6, 300), (9, 56.7675), (9, 150), (12, 60), (15, 100), (15, 400), (4, 500), (3, 800), (20, 60)]
KEYS = ["u_bending", "u_shear", "u_shear_buckling", "u_web_bearing", "u_deflection"]


@pytest.mark.parametrize("mode,ratio", [("variable", 360.0), ("variable", 200.0), ("total", 250.0)])
def test_reference_matches_checker(C, mode, ratio):
    K = Checker(C, replace(CheckerConfig(), deflection_load=mode, deflection_ratio=ratio))
    for L, w in CONTEXTS:
        e = K.evaluate(L, w)
        for i in range(len(C.names)):
            r = R.utilisations(C.cols, i, L, w, PHI_REF, mode, ratio)
            assert e["section_class"][i] == r["class"]
            for k in KEYS:
                assert e[k][i] == pytest.approx(r[k], rel=1e-9, abs=1e-12), (C.names[i], L, w, k)
            # bending-shear interaction: where V > Vpl the shear check already fails, and the two conventions for
            # rho differ (capped vs infeasible); both must be infeasible there
            if e["u_shear"][i] <= 1.0:
                assert e["u_bending_shear"][i] == pytest.approx(r["u_bending_shear"], rel=1e-9, abs=1e-12)
            else:
                assert e["u_bending_shear"][i] >= 1.0 or r["u_shear"] > 1.0
            ref_ok = max(r[k] for k in KEYS + ["u_bending_shear"]) <= 1.0 + 1e-9 and r["class"] <= 3
            assert bool(e["feasible"][i]) == bool(ref_ok), (C.names[i], L, w)


def test_bearing_rules_differ_only_where_two_solutions_exist(C):
    higher = Checker(C).F_Rd
    seq_checker = Checker(C, replace(CheckerConfig(), bearing_rule="sequential"))
    seq = seq_checker.F_Rd
    assert np.all(seq <= higher + 1e-9)
    differ = sorted(C.names[i] for i in range(len(C.names)) if abs(seq[i] - higher[i]) > 1e-9)
    assert differ == sorted(["1016x305x438", "1016x305x415", "914x305x381", "610x305x238", "305x127x48", "203x133x30"])
    for i in range(len(C.names)):
        h, tw, tf, b = (C.cols[k][i] for k in ("h", "tw", "tf", "b"))
        hw = h - 2 * tf
        assert seq[i] == pytest.approx(R.web_bearing_FRd(hw, tw, tf, b, seq_checker.fy[i], rule="sequential")[0], rel=1e-9)
        assert higher[i] == pytest.approx(R.web_bearing_FRd(hw, tw, tf, b, seq_checker.fy[i], rule="higher")[0], rel=1e-9)


def test_bearing_rule_validation():
    with pytest.raises(ValueError):
        CheckerConfig(bearing_rule="lower")
