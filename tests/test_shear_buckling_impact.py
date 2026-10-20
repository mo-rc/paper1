"""The unresolved difference in Vb,Rd for the shear-buckling sections (SCI AD 368: 1768 kN vs 1722 kN for 762x267x134)
cannot change feasibility: use the largest possible value (chi_w = 1) and compare. See docs/verification_record.md."""
import numpy as np
from dataclasses import replace
import pytest

from ub_rl.checker import Checker
from ub_rl.config import CheckerConfig


@pytest.mark.parametrize("mode,ratio", [("variable", 360.0), ("variable", 200.0), ("total", 250.0)])
def test_vb_rd_choice_never_changes_feasibility(Cplus, mode, ratio):
    cfg = replace(CheckerConfig(), deflection_load=mode, deflection_ratio=ratio)
    K, K2 = Checker(Cplus, cfg), Checker(Cplus, cfg)
    K2.Vbw = K.Vbw.copy()
    for n in ("762x267x134", "406x140x39"):
        i = Cplus.index_of(n)
        K2.Vbw[i] = K.fy[i] * K.hw[i] * K.tw[i] / np.sqrt(3.0) / 1e3  # chi_w = 1
    rng = np.random.default_rng(0)
    contexts = [(rng.uniform(9, 15), rng.uniform(56, 100)) for _ in range(1500)] + [(3, 800), (4, 500), (2, 1500), (6, 300)]
    for L, w in contexts:
        assert np.array_equal(K.evaluate(L, w)["feasible"], K2.evaluate(L, w)["feasible"])
