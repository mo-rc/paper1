import copy
import math

import numpy as np
import pytest

from ub_rl.checker import CHECKS, Checker
from ub_rl.config import CheckerConfig, E_STEEL

REF = (9.0, 56.7675)


def synth(C, name, **over):
    """One-row catalogue copied from a parsed row, with selected columns replaced."""
    S = C.subset([C.index_of(name)])
    S.cols = {k: v.copy() for k, v in S.cols.items()}
    for k, v in over.items():
        S.cols[k][:] = v
    return S


# ---------------------------------------------------------------- regression: reference case
def test_reference_case_lightest_is_457x191x74(C, Cplus):
    for S in (C, Cplus):
        K = Checker(S)
        i = K.lightest_feasible(*REF)
        assert S.names[i] == "457x191x74"
        r = K.check(*REF, i)
        assert r.feasible and r.governing == "bending"
        assert r.u_bending == pytest.approx(0.9983, abs=5e-4)  # regression pin of the current implementation
        assert r.section_class == 1 and r.fy == 355.0
        assert not r.shear_buckling_applies and r.u_shear_buckling == 0.0 and math.isnan(r.V_b_Rd)
        assert r.w_Ed == pytest.approx(REF[1] + 1.35 * 74.3 * 9.80665 / 1000)
        lighter = K.check(*REF, i - 1)
        assert not lighter.feasible and lighter.u_bending > 1.0


def test_reference_load_arithmetic():
    assert 1.35 * 22.05 + 1.5 * 18.0 == pytest.approx(56.7675)
    assert CheckerConfig().variable_share * 56.7675 / 1.5 == pytest.approx(18.0)


# ---------------------------------------------------------------- external benchmarks (SCI AD 368)
def test_shear_resistance_vs_blue_book(C):
    K = Checker(C)
    assert K.Vpl[C.index_of("406x140x39")] == pytest.approx(566, rel=0.005)
    assert K.Vpl[C.index_of("762x267x134")] == pytest.approx(1970, rel=0.005)


def test_shear_buckling_set_and_resistance(C, Cplus):
    for S in (C, Cplus):
        K = Checker(S)
        assert sorted(S.names[i] for i in np.where(K.sb)[0]) == ["406x140x39", "762x267x134"]
    K = Checker(C)
    j, k = C.index_of("406x140x39"), C.index_of("762x267x134")
    assert K.hw[j] / K.tw[j] == pytest.approx(59.5, abs=0.05) and K.hw[k] / K.tw[k] == pytest.approx(59.9, abs=0.05)
    assert K.Vbw[j] == pytest.approx(488, rel=0.01)  # AD 368 uses eps rounded to 0.81
    # AD 368 quotes 1768 kN for 762x267x134, which equals the cap eta*fy*hw*tw/sqrt(3) without chi_w.
    # The method it states gives less; the checker follows the stated method (docs/verification_record.md).
    cap = K.fy[k] * K.hw[k] * K.tw[k] / math.sqrt(3) / 1e3
    assert K.Vbw[k] < cap and K.Vbw[k] == pytest.approx(1722, rel=0.005)


def test_no_class3_or_4(C, Cplus):
    for S in (C, Cplus):
        K = Checker(S)
        assert (K.cls <= 2).all() and (K.cls == 2).sum() == 1


# ---------------------------------------------------------------- unit / boundary
@pytest.mark.parametrize("t,fy", [(8.0, 355), (16.0, 355), (16.01, 345), (40.0, 345), (40.01, 335), (63.0, 335), (63.01, 325), (80.0, 325)])
def test_fy_thresholds(C, t, fy):
    K = Checker(synth(C, "457x191x74", tf=t, tw=min(t, 9.0)))
    assert K.fy[0] == fy


def test_fy_above_80_rejected(C):
    with pytest.raises(ValueError):
        Checker(synth(C, "457x191x74", tf=81.0))


def test_class_boundaries(C):
    name = "457x191x74"
    eps = math.sqrt(235 / 355)
    cases = [(9 * eps, 1), (9 * eps + 1e-6, 2), (10 * eps, 2), (10 * eps + 1e-6, 3), (14 * eps, 3), (14 * eps + 1e-6, 4)]
    for ratio, cls in cases:
        assert Checker(synth(C, name, cf_tf=ratio)).cls[0] == cls
    for ratio, cls in [(72 * eps, 1), (72 * eps + 1e-6, 2), (83 * eps + 1e-6, 3), (124 * eps + 1e-6, 4)]:
        assert Checker(synth(C, name, cw_tw=ratio)).cls[0] == cls


def test_class4_infeasible_and_class3_uses_wel(C):
    eps = math.sqrt(235 / 355)
    K4 = Checker(synth(C, "457x191x74", cf_tf=14 * eps + 0.1))
    r = K4.check(9.0, 10.0, 0)
    assert not r.feasible and r.governing == "class4" and r.max_utilisation < 1
    K3 = Checker(synth(C, "457x191x74", cf_tf=10 * eps + 0.1))
    K1 = Checker(synth(C, "457x191x74"))
    assert K3.Mc[0] == pytest.approx(K3.Wel[0] * 355 / 1e6)
    assert K1.Mc[0] == pytest.approx(K1.Wpl[0] * 355 / 1e6)
    assert K3.check(9.0, 10.0, 0).feasible  # light load: class 3 is allowed


def test_class4_option_not_implemented():
    with pytest.raises(NotImplementedError):
        CheckerConfig(class4_treatment="effective")


def test_bending_boundary_exactly_one(C):
    K = Checker(C)
    i = C.index_of("457x191x74")
    L = 9.0
    g = K.self_w[i]
    w = 8 * K.Mc[i] / L ** 2 - 1.35 * g  # M_Ed = Mc,Rd
    r = K.check(L, w, i)
    assert r.u_bending == pytest.approx(1.0, abs=1e-12) and r.feasible
    assert not K.check(L, w * (1 + 1e-6), i).feasible
    assert K.check(L, w * (1 - 1e-6), i).feasible


def test_tolerance_is_applied(C):
    K = Checker(C)
    i = C.index_of("457x191x74")
    g = K.self_w[i]
    w = 8 * K.Mc[i] * (1 + 5e-10) / 81 - 1.35 * g
    assert K.check(9.0, w, i).feasible  # 1 + 5e-10 is within 1e-9
    assert not Checker(C, CheckerConfig(tol=0.0)).check(9.0, w, i).feasible


def test_bending_closed_form(C):
    K = Checker(C)
    i = C.index_of("457x191x74")
    L, w = 11.0, 70.0
    wEd = w + 1.35 * 74.3 * 9.80665e-3
    expect = wEd * L * L / 8 / (C["Wpl_y"][i] * 1e3 * 355 / 1e6)
    assert K.check(L, w, i).u_bending == pytest.approx(expect, rel=1e-12)


def test_shear_closed_form(C):
    K = Checker(C)
    i = C.index_of("457x191x74")
    c = C.cols
    Av = c["A"][i] * 100 - 2 * c["b"][i] * c["tf"][i] + (c["tw"][i] + 2 * c["r"][i]) * c["tf"][i]
    Av = max(Av, (c["h"][i] - 2 * c["tf"][i]) * c["tw"][i])
    r = K.check(9.0, 56.7675, i)
    assert r.V_pl_Rd == pytest.approx(Av * 355 / math.sqrt(3) / 1e3, rel=1e-12)
    assert r.u_shear == pytest.approx(r.V_Ed / r.V_pl_Rd, rel=1e-12)


def test_deflection_rules(C):
    i = C.index_of("457x191x74")
    L, w = 9.0, 56.7675
    Iy = C["Iy"][i] * 1e4
    base = Checker(C).check(L, w, i)
    assert base.deflection == pytest.approx(5 * 18.0 * (L * 1e3) ** 4 / (384 * E_STEEL * Iy), rel=1e-9)
    assert base.deflection_limit == pytest.approx(25.0)
    g = 74.3 * 9.80665e-3
    tot = Checker(C, CheckerConfig(deflection_load="total", deflection_ratio=250)).check(L, w, i)
    q = 18.0 + 22.05 + g
    assert tot.deflection == pytest.approx(5 * q * (L * 1e3) ** 4 / (384 * E_STEEL * Iy), rel=1e-9)
    assert tot.deflection_limit == pytest.approx(36.0)
    assert Checker(C, CheckerConfig(deflection_ratio=200)).check(L, w, i).u_deflection == pytest.approx(base.u_deflection * 200 / 360)


def test_self_weight_switch(C):
    i = C.index_of("457x191x74")
    a = Checker(C).check(*REF, i)
    b = Checker(C, CheckerConfig(self_weight=False)).check(*REF, i)
    assert b.w_Ed == pytest.approx(REF[1]) and a.w_Ed > b.w_Ed


def test_ltb_recorded(C):
    r = Checker(C).check(*REF, 10)
    assert r.chi_LT == 1.0 and "restraint" in r.ltb


# ---------------------------------------------------------------- interaction
def test_interaction_equals_bending_at_low_shear(C):
    K = Checker(C)
    r = K.check(15.0, 56.0, C.index_of("914x419x388"))
    assert r.u_bending_shear == pytest.approx(r.u_bending, rel=1e-12)


def test_interaction_exceeds_bending_at_high_shear(C):
    K = Checker(C)
    i = C.index_of("254x102x22")
    L = 3.0
    # choose w so that the support shear is 0.9 Vpl; ULS bending then is small, interaction is evaluated along the span
    wEd = 2 * 0.9 * K.Vpl[i] / L
    w = wEd - 1.35 * K.self_w[i]
    e = K.evaluate(L, w, [i])
    x = L * K.frac
    M = wEd * x * (L - x) / 2
    V = abs(wEd * (L / 2 - x))
    Vp = K.Vpl[i]
    rho = np.where(V > 0.5 * Vp, (2 * V / Vp - 1) ** 2, 0.0)
    Mv = np.minimum(K.Mc[i], (K.Wpl[i] - rho * K.Aw[i] ** 2 / (4 * K.tw[i])) * 355 / 1e6)
    assert e["u_bending_shear"][0] == pytest.approx((M / Mv).max(), rel=1e-12)
    assert e["u_bending_shear"][0] >= e["u_bending"][0]
    assert rho.max() > 0


def test_interaction_with_shear_buckling_section(C):
    K = Checker(C)
    j = C.index_of("406x140x39")
    L = 4.0
    wEd = 2 * 0.8 * K.Vbw[j] / L  # support shear = 0.8 Vbw > 0.5 Vbw
    e = K.evaluate(L, wEd - 1.35 * K.self_w[j], [j])
    assert e["u_shear_buckling"][0] == pytest.approx(0.8, rel=1e-9)
    assert np.isfinite(e["u_bending_shear"][0]) and e["u_bending_shear"][0] >= e["u_bending"][0] - 1e-12


def test_station_count_includes_midspan(C):
    for n in (3, 101, 201):
        K = Checker(C, CheckerConfig(n_stations=n))
        assert K.frac[(n - 1) // 2] == 0.5 and len(K.frac) == n
    with pytest.raises(ValueError):
        CheckerConfig(n_stations=100)


# ---------------------------------------------------------------- web bearing
def test_web_bearing_monotone_and_capped(C):
    prev = None
    res = {}
    for ss in (0.0, 25.0, 50.0, 100.0, 200.0):
        res[ss] = Checker(C, CheckerConfig(stiff_bearing_ss=ss)).F_Rd
    for a, b in zip((0.0, 25.0, 50.0, 100.0), (25.0, 50.0, 100.0, 200.0)):
        # a longer stiff bearing never lowers the resistance, except through the two-branch m2 rule (SCI AD 378)
        assert (res[b] >= res[a] * 0.99).all(), (a, b)
    K = Checker(C)
    big = Checker(C, CheckerConfig(stiff_bearing_ss=1e6))
    hwcap = Checker(C, CheckerConfig(stiff_bearing_ss=float(K.hw.max())))
    assert np.allclose(big.F_Rd, hwcap.F_Rd)  # ss limited to hw (EN 1993-1-5 6.3(1))
    assert np.isfinite(K.F_Rd).all() and (K.F_Rd > 0).all()


def test_web_bearing_hand_case(C):
    """457x191x74, ss = 100, c = 0, S355 hand arithmetic (stocky branch lambda_F <= 0.5 is checked)."""
    K = Checker(C)
    i = C.index_of("457x191x74")
    tw, tf, b, h = 9.0, 14.5, 190.4, 457.0
    hw = h - 2 * tf
    kF = min(2 + 6 * 100 / hw, 6)
    Fcr = 0.9 * kF * E_STEEL * tw ** 3 / hw
    le = min(kF * E_STEEL * tw ** 2 / (2 * 355 * hw), 100)
    m1 = b / tw
    for m2 in (0.0, 0.02 * (hw / tf) ** 2):
        ly = min(100 + 2 * tf * (1 + math.sqrt(m1 + m2)), le + tf * math.sqrt(m1 / 2 + (le / tf) ** 2 + m2), le + tf * math.sqrt(m1 + m2))
        lam = math.sqrt(ly * tw * 355 / Fcr)
        if (lam <= 0.5) == (m2 == 0.0):
            F = 355 * min(0.5 / lam, 1) * ly * tw / 1e3
            assert K.F_Rd[i] == pytest.approx(F, rel=1e-12)
            return
    pytest.fail("no self-consistent branch")


# ---------------------------------------------------------------- properties and interface
def test_utilisation_monotone_in_context(C):
    K = Checker(C)
    rng = np.random.default_rng(0)
    for _ in range(30):
        L, w = rng.uniform(9, 15), rng.uniform(56, 100)
        a = K.evaluate(L, w)["U"]
        b = K.evaluate(L * 1.05, w)["U"]
        c = K.evaluate(L, w * 1.05)["U"]
        assert (b >= a - 1e-12).all() and (c >= a - 1e-12).all()


def test_evaluate_matches_check_and_flags(C):
    K = Checker(C)
    L, w = 12.3, 77.7
    e = K.evaluate(L, w)
    for i in (0, 17, 40, 90):
        r = K.check(L, w, i)
        assert r.feasible == bool(e["feasible"][i])
        assert r.max_utilisation == pytest.approx(e["U"][i].max())
        assert r.max_utilisation <= 1 + 1e-9 or not r.feasible
        assert r.governing in CHECKS
        assert getattr(r, "u_" + r.governing) == pytest.approx(r.max_utilisation, abs=1e-9)
    sub = K.evaluate(L, w, [5, 6])
    assert np.allclose(sub["U"], e["U"][[5, 6]])


def test_context_validation(C):
    K = Checker(C)
    for bad in ((0.0, 50.0), (9.0, -1.0), (float("nan"), 50.0), (9.0, float("inf"))):
        with pytest.raises(ValueError):
            K.evaluate(*bad)


def test_eta_changes_shear_buckling_set(C):
    n12 = Checker(C, CheckerConfig(shear_eta=1.2)).sb.sum()
    assert n12 > Checker(C).sb.sum()  # larger eta lowers the 72 eps / eta limit


def test_enumeration_is_exact_over_ordered_catalogue(C):
    K = Checker(C)
    rng = np.random.default_rng(1)
    for _ in range(50):
        L, w = rng.uniform(9, 15), rng.uniform(56, 100)
        ok = K.evaluate(L, w)["feasible"]
        i = K.lightest_feasible(L, w)
        assert ok[i] and not ok[:i].any()
        assert (C["m"][ok] >= C["m"][i]).all()


def test_all_contexts_in_box_have_feasible_section(C):
    K = Checker(C)
    for L in (9, 15):
        for w in (56, 100):
            assert K.lightest_feasible(L, w) >= 0
