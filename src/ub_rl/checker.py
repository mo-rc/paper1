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
  LTB             restraint_ratio = 0: recorded, chi_LT = 1.0, no check (spec v1.2).
                  restraint_ratio > 0: EN 1993-1-1 6.3.2.3 (rolled I), Mcr per NCCI SN003 (spec amendment A1)
  deflection      7.2, 5 q L^4 / (384 E Iy) <= L / ratio
"""
from dataclasses import dataclass, asdict

import copy
from dataclasses import replace

import numpy as np

from .config import CheckerConfig, E_STEEL, G_ACC, G_STEEL
from .context import DEFLECTION_RULES

CHECKS = ("bending", "shear", "shear_buckling", "bending_shear", "web_bearing", "deflection", "ltb")
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
    # LTB (amendment A1); defaults keep v1.2 behaviour when restraint_ratio = 0
    u_ltb: float = 0.0
    M_cr: float = float("nan")  # kNm, nan when LTB is not evaluated
    M_b_Rd: float = float("nan")  # kNm, nan when LTB is not evaluated

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
        self.F_Rd, self.lam_F = _web_bearing(self.hw, tw, tf, b, self.fy, cfg.stiff_bearing_ss, cfg.bearing_c, gM1, cfg.bearing_rule)

        # LTB constants (used only if cfg.restraint_ratio > 0); Iw in dm6 -> mm6
        self.h = h
        self.Iz = c["Iz"] * 1e4
        self.It = c["It"] * 1e4
        self.Iw = c["Iw"] * 1e12
        self.W_ltb = np.where(self.cls <= 2, Wpl, Wel)
        # UK NA to 6.3.2.3, rolled I: curve b (h/b <= 2), c (2 < h/b <= 3.1), d (h/b > 3.1); alpha 0.34, 0.49, 0.76.
        # Verified against the Blue Book Mb,Rd table (docs/verification_record.md, Gate 2).
        self.alpha_LT = np.select([h / b <= 2.0, h / b <= 3.1], [0.34, 0.49], default=0.76)

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

        if cfg.restraint_ratio > 0:
            Mcr, chi, Mb = self._ltb(i, L, MEd)
            u_ltb = MEd / Mb
        else:
            Mcr = np.full(len(i), np.nan)
            chi = np.ones(len(i))
            Mb = np.full(len(i), np.nan)
            u_ltb = np.zeros(len(i))

        U = np.stack([u_bend, u_shear, u_sb, u_int, u_brg, u_def, u_ltb], axis=1)
        ok_class = self.cls[i] <= 3
        feasible = (U <= 1.0 + cfg.tol).all(axis=1) & ok_class
        return {
            "u_bending": u_bend, "u_shear": u_shear, "u_shear_buckling": u_sb, "u_bending_shear": u_int,
            "u_web_bearing": u_brg, "u_deflection": u_def, "U": U, "feasible": feasible,
            "section_class": self.cls[i], "w_Ed": wEd, "M_Ed": MEd, "V_Ed": VEd,
            "deflection": delta, "deflection_limit": np.full(len(i), dlim),
            "u_ltb": u_ltb, "M_cr": Mcr, "chi_LT": chi, "M_b_Rd": Mb,
        }

    def _ltb(self, i, L, MEd):
        """EN 1993-1-1 6.3.2.3 for rolled I sections, simply supported, UDL, restraint at the supports and at
        spacing Lcr = restraint_ratio * L (spec amendment A1). Returns (Mcr, chi_LT, Mb_Rd), kNm.

        C1 and kc are the UDL values only when the restraints are at the supports (restraint_ratio = 1); for
        intermediate restraints the conservative uniform-moment values are used (see CheckerConfig). LTB is ignored if
        lambda <= lambda0 or MEd/Mcr <= lambda0^2 (6.3.2.2(4)). See _ltb_core for the formulas."""
        cfg = self.cfg
        full_span = cfg.restraint_ratio >= 1.0
        return self._ltb_core(i, cfg.restraint_ratio * L * 1e3,
                              cfg.ltb_C1 if full_span else cfg.ltb_segment_C1, cfg.ltb_C2,
                              cfg.ltb_kc if full_span else cfg.ltb_segment_kc, cfg.ltb_load_position, MEd)

    def ltb_resistance(self, i, Lcr_m, C1=1.0, kc=None, C2=0.0, load_position="shear_centre"):
        """Mcr, chi_LT and Mb,Rd (kNm) for sections i at unrestrained length Lcr_m for a given C1, as tabulated in design
        tables (no MEd-dependent exemption). kc defaults to 1/sqrt(C1) (equals Table 6.6 for the UDL and point-load
        cases; treat as an assumption to confirm). Used by scripts/compare_bluebook.py."""
        i = np.atleast_1d(np.asarray(i, dtype=int))
        kc = 1.0 / np.sqrt(C1) if kc is None else kc
        return self._ltb_core(i, Lcr_m * 1e3, C1, C2, kc, load_position, None)

    def _ltb_core(self, i, Lcr, C1, C2, kc, load_position, MEd):
        """Mcr = C1 pi^2 E Iz / Lcr^2 * [ sqrt(Iw/Iz + Lcr^2 G It / (pi^2 E Iz) + (C2 zg)^2) - C2 zg ]  (NCCI SN003, k = kw = 1)
        zg = 0 (load at shear centre) or +h/2 (load on the top flange, destabilising).
        lambda = sqrt(W fy / Mcr); chi from Phi with alpha (curve b/c/d by h/b), lambda0, beta; chi <= 1, <= 1/lambda^2;
        modified by f (6.3.2.3(2)) with kc."""
        cfg = self.cfg
        Iz, It, Iw = self.Iz[i], self.It[i], self.Iw[i]
        zg = self.h[i] / 2.0 if load_position == "top_flange" else np.zeros(len(Iz))
        t = C2 * zg
        Mcr = C1 * np.pi ** 2 * E_STEEL * Iz / Lcr ** 2 * (
            np.sqrt(Iw / Iz + Lcr ** 2 * G_STEEL * It / (np.pi ** 2 * E_STEEL * Iz) + t ** 2) - t) / 1e6  # kNm
        W, fy = self.W_ltb[i], self.fy[i]
        Mrk = W * fy / 1e6  # kNm
        lam = np.sqrt(Mrk / Mcr)
        lam0, beta = cfg.ltb_lambda0, cfg.ltb_beta
        phi = 0.5 * (1.0 + self.alpha_LT[i] * (lam - lam0) + beta * lam ** 2)
        chi = 1.0 / (phi + np.sqrt(np.maximum(phi ** 2 - beta * lam ** 2, 0.0)))
        chi = np.minimum(np.minimum(chi, 1.0), 1.0 / lam ** 2)
        f = np.minimum(1.0 - 0.5 * (1.0 - kc) * (1.0 - 2.0 * (lam - 0.8) ** 2), 1.0)
        chi = np.minimum(chi / f, 1.0)
        no_ltb = lam <= lam0
        if MEd is not None:
            no_ltb = no_ltb | (MEd / Mcr <= lam0 ** 2)
        chi = np.where(no_ltb, 1.0, chi)
        return Mcr, chi, chi * Mrk / cfg.gamma_M1

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
            ltb=self._ltb_record(), chi_LT=float(e["chi_LT"][0]),
            w_Ed=float(e["w_Ed"][0]), M_Ed=float(e["M_Ed"][0]), V_Ed=float(e["V_Ed"][0]),
            M_c_Rd=float(self.Mc[i]), V_pl_Rd=float(self.Vpl[i]),
            V_b_Rd=float(self.Vbw[i]) if self.sb[i] else float("nan"),
            F_Rd=float(self.F_Rd[i]), deflection=float(e["deflection"][0]),
            deflection_limit=float(e["deflection_limit"][0]),
            u_ltb=float(U[6]), M_cr=float(e["M_cr"][0]), M_b_Rd=float(e["M_b_Rd"][0]),
        )

    def with_config(self, **changes):
        """Cheap copy sharing the section arrays, with changed run-time settings. Only settings read inside evaluate()
        may be changed (variable_share, restraint and LTB factors, deflection rule); those baked in at construction
        (bearing, shear eta, gammas used for precomputed resistances) require a new Checker."""
        new = copy.copy(self)
        new.cfg = replace(self.cfg, **changes)
        return new

    def evaluate_context(self, ctx, idx=None):
        """Evaluate every section (or idx) for a Context. 'feasible_code' = all code checks pass; 'feasible' also
        requires h <= depth_cap (a design requirement, not a code check)."""
        w, phi = ctx.factored_udl(self.cfg.gamma_G, self.cfg.gamma_Q)
        mode, ratio = DEFLECTION_RULES[ctx.deflection_rule]
        K = self.with_config(variable_share=phi, restraint_ratio=ctx.restraint_ratio,
                             deflection_load=mode, deflection_ratio=ratio)
        e = K.evaluate(ctx.span, w, idx)
        i = np.arange(len(self.h)) if idx is None else np.atleast_1d(np.asarray(idx))
        depth_ok = np.ones(len(i), bool) if ctx.depth_cap is None else self.h[i] <= ctx.depth_cap
        e["feasible_code"] = e["feasible"].copy()
        e["depth_ok"] = depth_ok
        e["feasible"] = e["feasible"] & depth_ok
        return e

    def lightest_feasible_context(self, ctx):
        """Index of the lightest feasible section in mass order, or -1 (abstain) if none is feasible, as lightest_feasible."""
        ok = self.evaluate_context(ctx)["feasible"]
        return int(np.argmax(ok)) if ok.any() else -1

    def _ltb_record(self):
        r = self.cfg.restraint_ratio
        if r > 0:
            return f"EN 1993-1-1 6.3.2.3, Lcr/L = {r:g}, load at {self.cfg.ltb_load_position}"
        return LTB_RECORD

    def lightest_feasible(self, L, w):
        """Enumeration over the catalogue in its own order; index of the first feasible section or -1.
        Catalogue must be mass-ordered (Catalogue.mass_ordered) for this to be the optimum of spec section 7."""
        ok = self.evaluate(L, w)["feasible"]
        return int(np.argmax(ok)) if ok.any() else -1


def _web_bearing(hw, tw, tf, bf, fy, ss, c, gM1, rule="higher"):
    """EN 1993-1-5 6.2-6.5, load type (c) (applied through one flange adjacent to an unstiffened end), kN.

    ss is limited to hw (6.3(1)). m2 depends on lambda_F, which depends on m2: both assumptions are evaluated.
    rule "higher" (default, SCI AD 378 and the Blue Book tables): a branch is valid only if it is self-consistent and
    the higher valid resistance is taken. rule "sequential" (EN text order, public SCI worked example): m2 = 0 unless
    lambda_F(m2 = 0) > 0.5, then the m2 > 0 result; it is lower where two valid solutions exist."""
    E = E_STEEL
    s = np.minimum(ss, hw)
    kF = np.minimum(2.0 + 6.0 * (s + c) / hw, 6.0)
    Fcr = 0.9 * kF * E * tw ** 3 / hw
    le = np.minimum(kF * E * tw ** 2 / (2.0 * fy * hw), s + c)
    m1 = fy * bf / (fy * tw)

    def branch(slender):
        m2 = 0.02 * (hw / tf) ** 2 if slender else np.zeros_like(hw)
        ly = np.minimum.reduce([
            s + 2.0 * tf * (1.0 + np.sqrt(m1 + m2)),
            le + tf * np.sqrt(m1 / 2.0 + (le / tf) ** 2 + m2),
            le + tf * np.sqrt(m1 + m2),
        ])
        lam = np.sqrt(ly * tw * fy / Fcr)
        chi = np.minimum(0.5 / lam, 1.0)
        return fy * chi * ly * tw / gM1 / 1e3, lam

    F0, lam0 = branch(False)
    F1, lam1 = branch(True)
    if rule == "sequential":
        return np.where(lam0 <= 0.5, F0, F1), np.where(lam0 <= 0.5, lam0, lam1)
    valid0, valid1 = lam0 <= 0.5, lam1 > 0.5
    best = np.where(valid0 & valid1, np.maximum(F0, F1), np.where(valid0, F0, np.where(valid1, F1, np.minimum(F0, F1))))
    lam_sel = np.where(valid0 & valid1, np.where(F0 >= F1, lam0, lam1), np.where(valid0, lam0, np.where(valid1, lam1, np.where(F0 <= F1, lam0, lam1))))
    return best, lam_sel
