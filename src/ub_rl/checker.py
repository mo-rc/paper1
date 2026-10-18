"""Eurocode 3 checker for a simply supported, laterally restrained UB under a UDL (spec sections 3, 5, 6).

Independent of any RL environment. Units: mm, N, N/mm2 inside; kN, kNm, m at the interface.
Every check returns a utilisation (demand / resistance). A design is feasible iff all are <= 1 + tol
and the section is not Class 4.

Clauses (BS EN 1993-1-1:2005+A1:2014 with UK NA; BS EN 1993-1-5:2006; sources in docs/verification_record.md):
  classification  Table 5.2 (bending: outstand flange 9/10/14 eps, internal web 72/83/124 eps)
  bending         6.2.5, class 1-2: Wpl fy; class 3: Wel fy
  shear           6.2.6, Av = A - 2 b tf + (tw + 2r) tf, not less than eta hw tw
  shear buckling  EN 1993-1-5 5.1(2), 5.2, 5.3 (transverse stiffeners at supports only, non-rigid end post,
                  flange contribution ignored), applies if hw/tw > 72 eps / eta
  interaction     6.2.8 at stations along the span; EN 1993-1-5 7.1 where shear buckling applies
  web bearing     EN 1993-1-5 6.2-6.5, type (c), unstiffened web, load at the end
  LTB             recorded: full restraint, chi_LT = 1.0, no check
  deflection      7.2, 5 q L^4 / (384 E Iy) <= L / ratio
"""
from dataclasses import dataclass, asdict

import numpy as np

from .config import CheckerConfig, E_STEEL, G_ACC

CHECKS = ("bending", "shear", "shear_buckling", "bending_shear", "web_bearing", "deflection")
LTB_RECORD = "continuous lateral restraint; chi_LT = 1.0; EN 1993-1-1 6.3.2 not applied"
CHI_LT = 1.0


@dataclass(frozen=True)
class CheckResult:
    """All numbers for one section in one context."""
    name: str
    mass: float  # kg/m
    L: float  # m
    w: float  # kN/m, factored superimposed UDL (self-weight excluded)
    feasible: bool
    governing: str
    max_utilisation: float
    # utilisations
    u_bending: float
    u_shear: float
    u_shear_buckling: float  # 0.0 where shear buckling does not apply
    u_bending_shear: float  # maximum over stations
    u_web_bearing: float
    u_deflection: float
    # section and material
    section_class: int
    fy: float
    shear_buckling_applies: bool
    ltb: str
    chi_LT: float
    # demands and resistances
    w_Ed: float  # kN/m including factored self-weight
    M_Ed: float
    V_Ed: float
    M_c_Rd: float
    V_pl_Rd: float
    V_b_Rd: float  # nan where shear buckling does not apply
    F_Rd: float
    deflection: float  # mm
    deflection_limit: float  # mm

    def as_dict(self):
        return asdict(self)


class Checker:
    """Precomputes every load-independent resistance for a catalogue, then evaluates contexts."""

    def __init__(self, catalogue, config=None):
        self.cat = catalogue
        self.cfg = config or CheckerConfig()
        c, cfg = catalogue.cols, self.cfg
        self.n = len(catalogue)
        self.mass = c["m"]
        h, b, tw, tf, r = c["h"], c["b"], c["tw"], c["tf"], c["r"]
        self.Iy = c["Iy"] * 1e4  # mm4
        Wpl, Wel = c["Wpl_y"] * 1e3, c["Wel_y"] * 1e3  # mm3
        A = c["A"] * 1e2  # mm2
        gM0, gM1, eta = cfg.gamma_M0, cfg.gamma_M1, cfg.shear_eta

        # Material (spec section 5): fy by maximum element thickness
        t = np.maximum(tf, tw)
        if (t > 80).any():
            raise ValueError("thickness above 80 mm: no S355 yield strength defined in spec section 5")
        self.fy = np.select([t <= 16, t <= 40, t <= 63], [355.0, 345.0, 335.0], default=325.0)
        eps = np.sqrt(235.0 / self.fy)
        self.eps = eps

        # Classification in bending (tabulated cf/tf and cw/tw)
        cf, cw = c["cf_tf"], c["cw_tw"]
        cls_f = np.select([cf <= 9 * eps, cf <= 10 * eps, cf <= 14 * eps], [1, 2, 3], default=4)
        cls_w = np.select([cw <= 72 * eps, cw <= 83 * eps, cw <= 124 * eps], [1, 2, 3], default=4)
        self.cls_flange, self.cls_web = cls_f, cls_w
        self.cls = np.maximum(cls_f, cls_w)

        # Bending resistance, kNm (class 4 gets the elastic value for information only; it is infeasible)
        self.Wpl, self.Wel = Wpl, Wel
        self.Mc = np.where(self.cls <= 2, Wpl, Wel) * self.fy / gM0 / 1e6
        self.Mpl = Wpl * self.fy / gM0 / 1e6
        self.Mf = b * tf * (h - tf) * self.fy / gM0 / 1e6  # flanges only, EN 1993-1-5 7.1

        # Shear, kN
        self.hw = h - 2 * tf
        self.Aw = self.hw * tw
        self.tw = tw
        Av = np.maximum(A - 2 * b * tf + (tw + 2 * r) * tf, eta * self.hw * tw)
        self.Av = Av
        self.Vpl = Av * self.fy / np.sqrt(3.0) / gM0 / 1e3

        # Shear buckling (non-rigid end post, transverse stiffeners at supports only)
        self.sb = self.hw / tw > 72 * eps / eta
        lam_w = self.hw / (86.4 * tw * eps)
        chi_w = np.minimum(eta, 0.83 / lam_w)  # Table 5.1, non-rigid end post
        Vbw = chi_w * self.fy * self.hw * tw / np.sqrt(3.0) / gM1 / 1e3
        Vcap = eta * self.fy * self.hw * tw / np.sqrt(3.0) / gM1 / 1e3
        self.Vbw = np.where(self.sb, np.minimum(Vbw, Vcap), np.inf)  # flange contribution ignored
        self.lam_w = lam_w

        # Web bearing, kN
        self.F_Rd, self.lam_F = _web_bearing(self.hw, tw, tf, b, self.fy, cfg.stiff_bearing_ss, cfg.bearing_c, gM1)

        self.self_w = self.mass * G_ACC / 1e3 if cfg.self_weight else np.zeros(self.n)  # kN/m
        self.frac = np.linspace(0.0, 1.0, cfg.n_stations)

    # ---------------------------------------------------------------- evaluation
    def evaluate(self, L, w, idx=None):
        """Utilisations for sections idx (default all) in context (L [m], w [kN/m]). Returns dict of arrays."""
        if not (np.isfinite(L) and np.isfinite(w) and L > 0 and w > 0):
            raise ValueError(f"context must be finite and positive, got L={L}, w={w}")
        cfg = self.cfg
        i = np.arange(self.n) if idx is None else np.atleast_1d(np.asarray(idx, dtype=int))
        g = self.self_w[i]
        wEd = w + cfg.gamma_G * g  # kN/m
        MEd = wEd * L * L / 8.0  # kNm
        VEd = wEd * L / 2.0  # kN
        Mc, Vpl, Vbw = self.Mc[i], self.Vpl[i], self.Vbw[i]
        sb = self.sb[i]

        u_bend = MEd / Mc
        u_shear = VEd / Vpl
        u_sb = np.where(sb, VEd / Vbw, 0.0)
        u_brg = VEd / self.F_Rd[i]

        # Deflection, characteristic loads (N/mm = kN/m)
        phi = cfg.variable_share
        Qk = phi * w / cfg.gamma_Q
        q = Qk + 0.0 * g if cfg.deflection_load == "variable" else Qk + (1.0 - phi) * w / cfg.gamma_G + g
        Lmm = L * 1e3
        delta = 5.0 * q * Lmm ** 4 / (384.0 * E_STEEL * self.Iy[i])
        dlim = Lmm / cfg.deflection_ratio
        u_def = delta / dlim

        u_int = self._interaction(i, L, wEd)

        U = np.stack([u_bend, u_shear, u_sb, u_int, u_brg, u_def], axis=1)
        ok_class = self.cls[i] <= 3
        feasible = (U <= 1.0 + cfg.tol).all(axis=1) & ok_class
        return {
            "u_bending": u_bend, "u_shear": u_shear, "u_shear_buckling": u_sb, "u_bending_shear": u_int,
            "u_web_bearing": u_brg, "u_deflection": u_def, "U": U, "feasible": feasible,
            "section_class": self.cls[i], "w_Ed": wEd, "M_Ed": MEd, "V_Ed": VEd,
            "deflection": delta, "deflection_limit": np.full(len(i), dlim),
        }

    def _interaction(self, i, L, wEd):
        """Maximum over stations of the bending-shear utilisation (6.2.8, or EN 1993-1-5 7.1 if shear buckling applies)."""
        x = L * self.frac  # m
        M = wEd[:, None] * x[None, :] * (L - x[None, :]) / 2.0  # kNm
        V = np.abs(wEd[:, None] * (L / 2.0 - x[None, :]))  # kN
        Mc, Vpl, cls = self.Mc[i][:, None], self.Vpl[i][:, None], self.cls[i][:, None]
        # 6.2.8: rho = (2 V / Vpl - 1)^2 when V > 0.5 Vpl; capped at 1 (shear > Vpl fails the shear check anyway)
        rho = np.where(V > 0.5 * Vpl, np.minimum((2.0 * V / Vpl - 1.0) ** 2, 1.0), 0.0)
        Mv = (self.Wpl[i][:, None] - rho * self.Aw[i][:, None] ** 2 / (4.0 * self.tw[i][:, None])) * self.fy[i][:, None] / self.cfg.gamma_M0 / 1e6
        Mv = np.minimum(Mc, Mv)
        # Class 3 with shear reduction is not implemented (no Class 3 section exists in the catalogue): infeasible
        unsupported = (cls == 3) & (rho > 0)
        u62 = np.where(unsupported, np.inf, M / np.where(unsupported, 1.0, Mv))
        # EN 1993-1-5 7.1 where shear buckling applies
        eta3 = V / self.Vbw[i][:, None]  # 0 where the section does not buckle (Vbw = inf)
        Mpl, Mf = self.Mpl[i][:, None], self.Mf[i][:, None]
        u71 = np.where(eta3 > 0.5, M / Mpl + (1.0 - Mf / Mpl) * (2.0 * eta3 - 1.0) ** 2, M / Mc)
        u = np.where(self.sb[i][:, None], u71, u62)
        return u.max(axis=1)

    def evaluate_all(self, L, w):
        return self.evaluate(L, w, None)

    def check(self, L, w, i):
        """Full record for section index i (position in this checker's catalogue)."""
        e = self.evaluate(L, w, [i])
        U = e["U"][0]
        cls = int(e["section_class"][0])
        feasible = bool(e["feasible"][0])
        top = float(U.max())
        if cls == 4:
            gov = "class4"
        else:
            gov = CHECKS[int(np.argmax(U >= top - 1e-12))]  # first check within 1e-12 of the maximum
        return CheckResult(
            name=self.cat.names[i], mass=float(self.mass[i]), L=float(L), w=float(w),
            feasible=feasible, governing=gov, max_utilisation=top,
            u_bending=float(U[0]), u_shear=float(U[1]), u_shear_buckling=float(U[2]),
            u_bending_shear=float(U[3]), u_web_bearing=float(U[4]), u_deflection=float(U[5]),
            section_class=cls, fy=float(self.fy[i]), shear_buckling_applies=bool(self.sb[i]),
            ltb=LTB_RECORD, chi_LT=CHI_LT,
            w_Ed=float(e["w_Ed"][0]), M_Ed=float(e["M_Ed"][0]), V_Ed=float(e["V_Ed"][0]),
            M_c_Rd=float(self.Mc[i]), V_pl_Rd=float(self.Vpl[i]),
            V_b_Rd=float(self.Vbw[i]) if self.sb[i] else float("nan"),
            F_Rd=float(self.F_Rd[i]), deflection=float(e["deflection"][0]),
            deflection_limit=float(e["deflection_limit"][0]),
        )

    def lightest_feasible(self, L, w):
        """Enumeration over the catalogue in its own order; index of the first feasible section or -1.
        Catalogue must be mass-ordered (Catalogue.mass_ordered) for this to be the optimum of spec section 7."""
        ok = self.evaluate(L, w)["feasible"]
        return int(np.argmax(ok)) if ok.any() else -1


def _web_bearing(hw, tw, tf, bf, fy, ss, c, gM1):
    """EN 1993-1-5 6.2-6.5, load type (c) (applied through one flange adjacent to an unstiffened end), kN.

    ss is limited to hw (6.3(1)). m2 depends on lambda_F, which depends on m2: both assumptions are evaluated
    and a branch is valid only if it is self-consistent; the higher valid resistance is taken (SCI AD 378)."""
    E = E_STEEL
    s = np.minimum(ss, hw)
    kF = np.minimum(2.0 + 6.0 * (s + c) / hw, 6.0)
    Fcr = 0.9 * kF * E * tw ** 3 / hw
    le = np.minimum(kF * E * tw ** 2 / (2.0 * fy * hw), s + c)
    m1 = fy * bf / (fy * tw)
    best = np.full_like(hw, -np.inf)
    worst = np.full_like(hw, np.inf)
    lam_sel = np.zeros_like(hw)
    for slender in (False, True):
        m2 = 0.02 * (hw / tf) ** 2 if slender else np.zeros_like(hw)
        ly = np.minimum.reduce([
            s + 2.0 * tf * (1.0 + np.sqrt(m1 + m2)),
            le + tf * np.sqrt(m1 / 2.0 + (le / tf) ** 2 + m2),
            le + tf * np.sqrt(m1 + m2),
        ])
        lam = np.sqrt(ly * tw * fy / Fcr)
        chi = np.minimum(0.5 / lam, 1.0)
        F = fy * chi * ly * tw / gM1 / 1e3
        valid = (lam > 0.5) if slender else (lam <= 0.5)
        take = valid & (F > best)
        lam_sel = np.where(take, lam, lam_sel)
        best = np.where(valid, np.maximum(best, F), best)
        worst = np.minimum(worst, F)
    # At least one branch is valid by construction (larger m2 gives larger lambda_F); fall back to the lower value
    return np.where(np.isfinite(best), best, worst), lam_sel
