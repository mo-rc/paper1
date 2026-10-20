"""Second, scalar implementation of the LTB check, written separately from the vectorised one (Gate 2 evidence, part 1).
It uses plain Python floats and loops and restates EN 1993-1-1 6.3.2.3 and NCCI SN003 directly. It shares the catalogue
and classification with the checker, so it checks the LTB arithmetic only. The Blue Book Mb,Rd comparison is still open."""
import math
from dataclasses import replace

import numpy as np
import pytest

from ub_rl.checker import Checker
from ub_rl.config import CheckerConfig

E, G = 210000.0, 210000.0 / (2 * 1.3)


def mb_scalar(name_idx, K, C, L_m, w_ed_total, rho, top_flange, udl_factors_for_segments=False):
    c = C.cols
    i = name_idx
    h, b, tw, tf = c["h"][i], c["b"][i], c["tw"][i], c["tf"][i]
    t_max = max(tf, tw)
    fy = 355.0 if t_max <= 16 else 345.0 if t_max <= 40 else 335.0 if t_max <= 63 else 325.0
    W = (c["Wpl_y"][i] if K.cls[i] <= 2 else c["Wel_y"][i]) * 1e3
    Iz, It, Iw = c["Iz"][i] * 1e4, c["It"][i] * 1e4, c["Iw"][i] * 1e12
    Lcr = rho * L_m * 1000.0
    full = rho >= 1.0
    C1 = 1.127 if (full or udl_factors_for_segments) else 1.0
    kc = 0.94 if (full or udl_factors_for_segments) else 1.0
    zg = h / 2.0 if top_flange else 0.0
    a = 0.454 * zg
    mcr = C1 * math.pi ** 2 * E * Iz / Lcr ** 2 * (math.sqrt(Iw / Iz + Lcr ** 2 * G * It / (math.pi ** 2 * E * Iz) + a * a) - a) / 1e6
    mrk = W * fy / 1e6
    lam = math.sqrt(mrk / mcr)
    MEd = w_ed_total * L_m ** 2 / 8.0
    if lam <= 0.4 or MEd / mcr <= 0.16:
        chi = 1.0
    else:
        alpha = 0.34 if h / b <= 2.0 else (0.49 if h / b <= 3.1 else 0.76)
        phi = 0.5 * (1 + alpha * (lam - 0.4) + 0.75 * lam * lam)
        chi = 1.0 / (phi + math.sqrt(phi * phi - 0.75 * lam * lam))
        chi = min(chi, 1.0, 1.0 / (lam * lam))
        f = min(1.0 - 0.5 * (1.0 - kc) * (1.0 - 2.0 * (lam - 0.8) ** 2), 1.0)
        chi = min(chi / f, 1.0)
    return mcr, chi, chi * mrk, MEd


@pytest.mark.parametrize("rho", [0.25, 1 / 3, 0.5, 1.0])
@pytest.mark.parametrize("top", [False, True])
def test_scalar_reference_agrees_with_vectorised_ltb(C, rho, top):
    K = Checker(C, replace(CheckerConfig(), restraint_ratio=rho, ltb_load_position="top_flange" if top else "shear_centre"))
    rng = np.random.default_rng(11)
    for _ in range(6):
        L = rng.uniform(6.0, 15.0)
        w = rng.uniform(40.0, 100.0)
        e = K.evaluate(L, w)
        w_tot = w + 1.35 * C.cols["m"] * 9.80665e-3  # factored superimposed + factored self-weight, kN/m
        for i in range(len(C.names)):
            if K.cls[i] > 3:
                continue
            mcr, chi, mb, MEd = mb_scalar(i, K, C, L, w_tot[i], rho, top)
            assert e["M_cr"][i] == pytest.approx(mcr, rel=1e-9)
            assert e["chi_LT"][i] == pytest.approx(chi, rel=1e-9)
            assert e["M_b_Rd"][i] == pytest.approx(mb, rel=1e-9)
            assert e["u_ltb"][i] == pytest.approx(MEd / mb, rel=1e-9)
