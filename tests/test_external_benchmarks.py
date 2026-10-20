"""Checks against numbers published by the Steel Construction Institute (public; not the Blue Book tables themselves).

Sources: SCI Advisory Desk AD 368 (shear resistance of I-sections in P363) and AD 378 (web resistance to transverse loads).
The Blue Book member-resistance tables are still needed for Gate 2; see docs/verification_record.md."""
import numpy as np
import pytest

from ub_rl.checker import Checker


def _k(C, name):
    K = Checker(C)
    return K, C.names.index(name)


def test_ad368_shear_resistance_values(C):
    """AD 368: the Blue Book gives Vc,Rd = 566 kN (406x140x39) and 1970 kN (762x267x134), S355. The workbook tabulates
    section properties to three significant figures, so agreement is expected to about 0.3 %."""
    K, i = _k(C, "406x140x39")
    assert K.Vpl[i] == pytest.approx(566.0, rel=3e-3)
    K, j = _k(C, "762x267x134")
    assert K.Vpl[j] == pytest.approx(1970.0, rel=3e-3)


def test_ad368_only_two_sections_need_shear_buckling(C):
    K = Checker(C)
    assert sorted(C.names[i] for i in np.where(K.sb)[0]) == ["406x140x39", "762x267x134"]
    i = C.names.index("406x140x39")
    assert K.hw[i] / K.tw[i] == pytest.approx(59.5, abs=0.05)
    j = C.names.index("762x267x134")
    assert K.hw[j] / K.tw[j] == pytest.approx(59.9, abs=0.05)


def test_ad368_shear_buckling_406x140x39(C):
    """AD 368 worked example: Vbw,Rd = 488 kN from lambda_w = 0.85 and chi_w = 0.976 (intermediate values rounded in the
    note); the unrounded calculation gives 489.8 kN. The cap eta fy hw tw / sqrt(3) is 500 kN."""
    K, i = _k(C, "406x140x39")
    assert K.Vbw[i] == pytest.approx(488.0, rel=5e-3)
    assert K.lam_w[i] == pytest.approx(0.85, abs=0.01)
    cap = 355.0 * K.hw[i] * K.tw[i] / np.sqrt(3.0) / 1e3
    assert cap == pytest.approx(500.0, rel=2e-3) and K.Vbw[i] < cap


def test_ad368_762x267x134_known_discrepancy(C):
    """AD 368 quotes Vb,Rd = 1768 kN for the 762x267x134. That value equals the cap eta fy hw tw / sqrt(3) (chi_w = 1),
    but the method stated in the note gives lambda_w = 0.85 > 0.83 and chi_w = 0.97, hence about 1722 kN. The cause is
    unresolved (typographical or an unstated input). The checker keeps the lower value, which is conservative. This test
    documents the gap; it must be revisited at Gate 2 against the Blue Book table."""
    K, i = _k(C, "762x267x134")
    cap = 355.0 * K.hw[i] * K.tw[i] / np.sqrt(3.0) / 1e3
    assert cap == pytest.approx(1768.0, rel=2e-3)
    assert K.Vbw[i] == pytest.approx(1722.0, rel=3e-3)
    assert K.Vbw[i] < 1768.0 and K.Vbw[i] > 0.95 * 1768.0


def test_s355_design_strength_bands(C):
    """Blue Book / Orange Book notes: S355 design strength 355, 345, 335, 325 N/mm2 for t <= 16, 40, 63, 80 mm."""
    K = Checker(C)
    t = np.maximum(C.cols["tf"], C.cols["tw"])
    assert np.all(K.fy[t <= 16] == 355.0) and np.all(K.fy[(t > 16) & (t <= 40)] == 345.0)
    assert np.all(K.fy[(t > 40) & (t <= 63)] == 335.0) and np.all(K.fy[(t > 63) & (t <= 80)] == 325.0)


def test_eta_is_one(C):
    """UK NA to EN 1993-1-5 NA.2.4: eta = 1.0 (AD 368)."""
    assert Checker(C).cfg.shear_eta == 1.0
