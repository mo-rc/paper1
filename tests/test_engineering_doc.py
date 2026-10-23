"""docs/engineering_concepts.md cites code names and result keys; fail if the code drifts from the document."""
import os
import numpy as np
from ub_rl import config
from ub_rl.checker import Checker

DOC = open(os.path.join(os.path.dirname(__file__), "..", "docs", "engineering_concepts.md"), encoding="utf-8").read()
ATTRS = ["fy", "eps", "cls", "Mc", "Vpl", "Vbw", "F_Rd", "Iy", "Iz", "It", "Iw", "Wpl", "Wel", "hw", "Av", "sb", "alpha_LT", "self_w"]
KEYS = ["u_bending", "u_shear", "u_shear_buckling", "u_bending_shear", "u_web_bearing", "u_deflection", "u_ltb", "U", "feasible",
        "section_class", "w_Ed", "M_Ed", "V_Ed", "deflection", "M_cr"]


def test_documented_attributes_exist_and_are_cited(C):
    K = Checker(C)
    for a in ATTRS:
        assert hasattr(K, a), a
        assert f"`Checker.{a}`" in DOC, a


def test_documented_result_keys_are_returned_and_cited(C):
    K = Checker(C, config=Checker(C).cfg.__class__(restraint_ratio=0.5))
    e = K.evaluate(9.0, 56.7675)
    for k in KEYS:
        assert k in e, k
        assert k in DOC, k


def test_documented_constants():
    assert config.E_STEEL == 210000.0 and abs(config.G_STEEL - 80769.23) < 0.01
    assert "80 769" in DOC and "210 000" in DOC and "56.7675" in DOC
    assert abs(config.PHI_REF - 27.0 / 56.7675) < 1e-12
