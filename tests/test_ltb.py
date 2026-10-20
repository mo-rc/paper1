"""LTB tests (spec amendment A1). Not Gate 2: Blue Book Mb,Rd comparison and a second implementation are still required."""
import math
from dataclasses import replace

import numpy as np
import pytest

from ub_rl.checker import Checker
from ub_rl.config import CheckerConfig, E_STEEL, G_STEEL

L, W = 9.0, 56.7675


def _K(C, **kw):
    return Checker(C, replace(CheckerConfig(), **kw))


def _idx(C, name):
    return C.names.index(name)


def _scalar_mcr(Iz, It, Iw, Lcr, C1=1.127, C2=0.454, zg=0.0):
    """Independent scalar re-statement of the NCCI SN003 expression (units mm, N/mm2; result kNm)."""
    t = C2 * zg
    return C1 * math.pi ** 2 * E_STEEL * Iz / Lcr ** 2 * (
        math.sqrt(Iw / Iz + Lcr ** 2 * G_STEEL * It / (math.pi ** 2 * E_STEEL * Iz) + t ** 2) - t) / 1e6


def test_default_is_continuous_restraint(C):
    K = Checker(C)
    e = K.evaluate(L, W)
    assert e["U"].shape[1] == 7 and np.all(e["u_ltb"] == 0.0) and np.all(e["chi_LT"] == 1.0)
    r = K.check(L, W, _idx(C, "457x191x74"))
    assert r.chi_LT == 1.0 and "restraint" in r.ltb and r.u_ltb == 0.0


def test_tiny_restraint_length_changes_nothing(C):
    base = Checker(C).evaluate(L, W)
    tiny = _K(C, restraint_ratio=1e-4).evaluate(L, W)
    assert np.array_equal(base["feasible"], tiny["feasible"])
    assert np.allclose(tiny["chi_LT"], 1.0)


@pytest.mark.parametrize("name", ["457x191x74", "610x229x125", "356x171x51"])
@pytest.mark.parametrize("ratio", [0.25, 0.5, 1.0])
def test_mcr_matches_scalar_formula(C, name, ratio):
    K = _K(C, restraint_ratio=ratio)
    i = _idx(C, name)
    e = K.evaluate(L, W, [i])
    C1 = 1.127 if ratio >= 1.0 else 1.0  # intermediate restraints: conservative uniform-moment factor
    ref = _scalar_mcr(K.Iz[i], K.It[i], K.Iw[i], ratio * L * 1e3, C1=C1)
    assert e["M_cr"][0] == pytest.approx(ref, rel=1e-12)


def test_top_flange_loading_reduces_mcr(C):
    i = _idx(C, "457x191x74")
    a = _K(C, restraint_ratio=1.0).evaluate(L, W, [i])["M_cr"][0]
    b = _K(C, restraint_ratio=1.0, ltb_load_position="top_flange").evaluate(L, W, [i])["M_cr"][0]
    assert b < a
    K = _K(C, restraint_ratio=1.0, ltb_load_position="top_flange")
    assert b == pytest.approx(_scalar_mcr(K.Iz[i], K.It[i], K.Iw[i], L * 1e3, zg=K.h[i] / 2.0), rel=1e-12)


def test_chi_bounds_and_mb_not_above_mc(C):
    for ratio in (0.25, 0.5, 1.0):
        e = _K(C, restraint_ratio=ratio).evaluate(L, W)
        assert np.all(e["chi_LT"] > 0) and np.all(e["chi_LT"] <= 1.0 + 1e-12)
        K = Checker(C)
        assert np.all(e["M_b_Rd"] <= K.Mc * (1 + 1e-12))


def test_utilisation_monotone_in_restraint_spacing(C):
    prev = None
    for ratio in (0.25, 1 / 3, 0.5, 1.0):
        u = _K(C, restraint_ratio=ratio).evaluate(L, W)["u_ltb"]
        if prev is not None:
            assert np.all(u >= prev - 1e-12)
        prev = u


def test_feasible_set_shrinks_and_reference_section_fails_when_unrestrained(C):
    base = Checker(C).evaluate(L, W)["feasible"]
    full = _K(C, restraint_ratio=1.0).evaluate(L, W)["feasible"]
    assert full.sum() < base.sum() and not np.any(full & ~base)
    i = _idx(C, "457x191x74")
    assert base[i] and not full[i]


def test_ltb_governs_when_unrestrained(C):
    K = _K(C, restraint_ratio=1.0)
    r = K.check(L, W, _idx(C, "457x191x74"))
    assert r.governing == "ltb" and r.u_ltb > 1.0 and r.chi_LT < 1.0 and "6.3.2.3" in r.ltb


def test_curve_selection_by_h_over_b(C, Cplus):  # UK NA: curve d above h/b = 3.1 (confirmed by the Blue Book table, Gate 2)
    K = Checker(C)
    h, b = C.cols["h"], C.cols["b"]
    hb = h / b
    assert np.all(K.alpha_LT[hb <= 2.0] == 0.34)
    assert np.all(K.alpha_LT[(hb > 2.0) & (hb <= 3.1)] == 0.49)
    assert np.all(K.alpha_LT[hb > 3.1] == 0.76)
    hb_all = Cplus.cols["h"] / Cplus.cols["b"]
    assert (hb_all > 3.1).sum() == 16 and (hb > 3.1).sum() == 10  # 10 in C (1016x305 series); 533x165 and 610x178 are '+' rows


def test_ltb_config_validation():
    with pytest.raises(ValueError):
        CheckerConfig(restraint_ratio=1.5)
    with pytest.raises(ValueError):
        CheckerConfig(ltb_load_position="bottom")


def test_enumeration_exact_with_ltb(C):
    K = _K(C, restraint_ratio=0.5)
    i = K.lightest_feasible(L, W)
    ok = K.evaluate(L, W)["feasible"]
    assert ok[i] and not ok[:i].any()


@pytest.mark.parametrize("ratio", [0.25, 1 / 3, 0.5])
def test_intermediate_restraint_is_not_less_conservative_than_udl_factors(C, ratio):
    seg = _K(C, restraint_ratio=ratio).evaluate(L, W)
    udl = _K(C, restraint_ratio=ratio, ltb_segment_C1=1.127, ltb_segment_kc=0.94).evaluate(L, W)
    assert np.all(seg["u_ltb"] >= udl["u_ltb"] - 1e-12)
    assert np.all(seg["M_cr"] <= udl["M_cr"] + 1e-9)


def test_full_span_uses_udl_factors_and_ignores_segment_factors(C):
    a = _K(C, restraint_ratio=1.0).evaluate(L, W)["u_ltb"]
    b = _K(C, restraint_ratio=1.0, ltb_segment_C1=9.0, ltb_segment_kc=0.5).evaluate(L, W)["u_ltb"]
    assert np.array_equal(a, b)


def test_reference_optimum_by_restraint_ratio(C):
    """Exploratory values (unvalidated until Gate 2): shear-centre loading, self-weight included, 56.7675 kN/m, 9 m."""
    expected = {0.0: "457x191x74", 0.25: "533x210x82", 1 / 3: "533x210x92", 0.5: "610x229x101", 1.0: "686x254x140"}
    for ratio, name in expected.items():
        K = _K(C, restraint_ratio=ratio)
        assert C.names[K.lightest_feasible(L, W)] == name


def test_public_ltb_resistance_matches_internal_ltb_for_full_span(C):
    """ltb_resistance (used for table comparison) agrees with the evaluate() path when no MEd exemption applies."""
    K = _K(C, restraint_ratio=1.0)
    e = K.evaluate(L, 90.0)  # heavy load so MEd/Mcr exceeds the exemption for most sections
    Mcr, chi, Mb = K.ltb_resistance(np.arange(len(C.names)), L, C1=1.127, kc=0.94)
    keep = e["M_Ed"] / e["M_cr"] > 0.16
    assert np.allclose(Mcr, e["M_cr"], rtol=1e-12) and np.allclose(chi[keep], e["chi_LT"][keep], rtol=1e-12)
    assert np.allclose(Mb[keep], e["M_b_Rd"][keep], rtol=1e-12)
    assert np.all(chi <= 1.0) and np.all(Mb <= Checker(C).Mc * (1 + 1e-12))
