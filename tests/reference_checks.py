"""Second implementation of the non-LTB checks (Gate 2 evidence, part 2).

Written separately from src/ub_rl/checker.py: plain Python floats and loops, one section at a time, following the clause
text of EN 1993-1-1 and EN 1993-1-5 (and the public SCI worked examples) rather than the vectorised code. It reads the
same catalogue columns, so it checks the checker's arithmetic and its reading of the clauses, but it is by the same
author team and does not replace the Blue Book comparison or an independent engineer's hand calculations."""
import math

E = 210000.0
G_ACC = 9.80665


def fy_of(tf, tw):
    t = max(tf, tw)  # SCI Blue Book convention: maximum element thickness
    return 355.0 if t <= 16 else 345.0 if t <= 40 else 335.0 if t <= 63 else 325.0


def web_bearing_FRd(hw, tw, tf, bf, fy, ss=100.0, c=0.0, gM1=1.0, rule="higher"):
    """EN 1993-1-5 6.2 to 6.5, type (c). m2 = 0.02 (hw/tf)^2 if lambda_F > 0.5 and 0 otherwise, but lambda_F depends on m2,
    so two assumptions are evaluated.
    rule = "higher": SCI AD 378 and the Blue Book tables: a branch is valid if its result is consistent with its own
        assumption (m2 = 0 needs lambda_F <= 0.5; m2 > 0 needs lambda_F > 0.5); if two valid solutions exist the higher
        resistance may be taken. If neither is valid (not expected) the lower resistance is used.
    rule = "sequential": the order shown in the public SCI worked example: evaluate with m2 = 0; only if lambda_F > 0.5
        recompute with m2 > 0 and use that result. Lower (conservative) where two valid solutions exist."""
    s = min(ss, hw)
    kF = min(2.0 + 6.0 * (s + c) / hw, 6.0)  # 6.1(3), Eq 6.13
    Fcr = 0.9 * kF * E * tw ** 3 / hw  # 6.4(1)
    le = min(kF * E * tw ** 2 / (2.0 * fy * hw), s + c)  # Eq 6.13
    m1 = fy * bf / (fy * tw)  # Eq 6.8

    def branch(m2):
        ly = min(s + 2.0 * tf * (1.0 + math.sqrt(m1 + m2)),  # Eq 6.10
                 le + tf * math.sqrt(m1 / 2.0 + (le / tf) ** 2 + m2),  # Eq 6.11
                 le + tf * math.sqrt(m1 + m2))  # Eq 6.12
        lam = math.sqrt(ly * tw * fy / Fcr)
        return fy * min(0.5 / lam, 1.0) * ly * tw / gM1 / 1000.0, lam

    F0, lam0 = branch(0.0)
    F1, lam1 = branch(0.02 * (hw / tf) ** 2)
    if rule == "sequential":
        return (F0, lam0) if lam0 <= 0.5 else (F1, lam1)
    valid = [(F, lam) for (F, lam), ok in (((F0, lam0), lam0 <= 0.5), ((F1, lam1), lam1 > 0.5)) if ok]
    if valid:
        return max(valid)
    return min((F0, lam0), (F1, lam1))


def utilisations(cols, i, L, w, phi, defl_mode="variable", defl_ratio=360.0, self_weight=True, n_stations=101,
                 bearing_rule="higher", ss=100.0, c=0.0):
    """Utilisations of section i (position in the catalogue columns) for factored superimposed UDL w (kN/m), span L (m).
    phi = variable share of w. Returns dict; 'class' is the section class (4 = infeasible)."""
    h, b, tw, tf, r = (cols[k][i] for k in ("h", "b", "tw", "tf", "r"))
    A = cols["A"][i] * 100.0
    Iy = cols["Iy"][i] * 1e4
    Wpl, Wel = cols["Wpl_y"][i] * 1e3, cols["Wel_y"][i] * 1e3
    fy = fy_of(tf, tw)
    eps = math.sqrt(235.0 / fy)
    eta = 1.0
    # classification (bending): outstand flange and web, Table 5.2
    cf = (b - tw - 2.0 * r) / 2.0 / tf
    cw = cols["d"][i] / tw
    cls_f = 1 if cf <= 9 * eps else 2 if cf <= 10 * eps else 3 if cf <= 14 * eps else 4
    cls_w = 1 if cw <= 72 * eps else 2 if cw <= 83 * eps else 3 if cw <= 124 * eps else 4
    cls = max(cls_f, cls_w)
    # actions
    g = cols["m"][i] * G_ACC / 1000.0 if self_weight else 0.0  # kN/m
    wEd = w + 1.35 * g
    L_mm = L * 1000.0
    # bending
    Mc = (Wpl if cls <= 2 else Wel) * fy / 1e6
    Mpl = Wpl * fy / 1e6
    MEd = wEd * L * L / 8.0
    VEd = wEd * L / 2.0
    # shear
    hw = h - 2.0 * tf
    Av = max(A - 2.0 * b * tf + (tw + 2.0 * r) * tf, eta * hw * tw)
    Vpl = Av * fy / math.sqrt(3.0) / 1000.0
    # shear buckling, EN 1993-1-5 5.1(2), 5.2, 5.3(3) stiffeners at supports only, Table 5.1 non-rigid end post
    sb = hw / tw > 72.0 * eps / eta
    Vbw = math.inf
    if sb:
        lam_w = hw / (86.4 * tw * eps)
        chi_w = eta if lam_w < 0.83 / eta else 0.83 / lam_w
        Vbw = min(chi_w * fy * hw * tw / math.sqrt(3.0), eta * fy * hw * tw / math.sqrt(3.0)) / 1000.0
    # web bearing
    FRd, _ = web_bearing_FRd(hw, tw, tf, b, fy, ss, c, 1.0, bearing_rule)
    # deflection (characteristic)
    Qk = phi * w / 1.5
    Gk_super = (1.0 - phi) * w / 1.35
    q = Qk if defl_mode == "variable" else Qk + Gk_super + g
    delta = 5.0 * q * L_mm ** 4 / (384.0 * E * Iy)
    u_def = delta / (L_mm / defl_ratio)
    # interaction at stations
    Aw = hw * tw
    Mf = b * tf * (h - tf) * fy / 1e6
    u_int = 0.0
    for k in range(n_stations):
        x = L * k / (n_stations - 1)
        V = wEd * (L / 2.0 - x)
        M = wEd * x * (L - x) / 2.0
        V = abs(V)
        if sb:
            eta3 = V / Vbw
            if eta3 > 0.5:
                u = M / Mpl + (1.0 - Mf / Mpl) * (2.0 * eta3 - 1.0) ** 2  # EN 1993-1-5 Eq 7.1 rearranged
            else:
                u = M / Mc
        else:
            if V > 0.5 * Vpl:
                if cls == 3 or V > Vpl:
                    u = math.inf  # Class 3 with high shear not supported (none in the catalogue); V > Vpl fails the shear check
                else:
                    rho = (2.0 * V / Vpl - 1.0) ** 2
                    Mv = min((Wpl - rho * Aw ** 2 / (4.0 * tw)) * fy / 1e6, Mc)  # Eq 6.30
                    u = M / Mv
            else:
                u = M / Mc
        u_int = max(u_int, u)
    return {
        "class": cls, "u_bending": MEd / Mc, "u_shear": VEd / Vpl, "u_shear_buckling": VEd / Vbw if sb else 0.0,
        "u_bending_shear": u_int, "u_web_bearing": VEd / FRd, "u_deflection": u_def,
        "M_c_Rd": Mc, "V_pl_Rd": Vpl, "V_b_Rd": Vbw, "F_Rd": FRd, "M_Ed": MEd, "V_Ed": VEd, "fy": fy,
    }
