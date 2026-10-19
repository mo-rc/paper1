"""Checker configuration. Every open assumption of spec section 15 is a parameter here.

Defaults are the working assumptions of the spec. They are not approvals."""
from dataclasses import dataclass, asdict

E_STEEL = 210_000.0  # N/mm2
G_STEEL = 81_000.0  # N/mm2 (shear modulus, EN 1993-1-1 3.2.6)
G_ACC = 9.80665  # m/s2, mass per metre (kg/m) -> weight per metre (kN/m)
PHI_REF = 27.0 / 56.7675  # variable share of the factored superimposed load (spec section 3)


@dataclass(frozen=True)
class CheckerConfig:
    # Load combination (spec 15: 1.35 dead, 1.5 live)
    gamma_G: float = 1.35
    gamma_Q: float = 1.5
    # Fixed variable share of the factored superimposed UDL (spec 15)
    variable_share: float = PHI_REF
    # Self-weight added by the checker (spec 15)
    self_weight: bool = True
    # Deflection (spec 6 and 15): "variable" or "total" characteristic load, limit = span / ratio
    deflection_load: str = "variable"
    deflection_ratio: float = 360.0
    # Support and bearing (spec 6 and 15): fork supports, unstiffened web, load at the beam end
    support: str = "fork"
    stiff_bearing_ss: float = 100.0  # mm
    bearing_c: float = 0.0  # mm, distance from the end of the stiff bearing to the end of the section
    # Shear area / shear buckling factor eta (spec 15; UK NA to EN 1993-1-5 NA.2.4)
    shear_eta: float = 1.0
    # Class 4 treatment (spec 6 and 15): only "infeasible" is implemented
    class4_treatment: str = "infeasible"
    # Lateral-torsional buckling (spec amendment A1). restraint_ratio = Lcr / L; 0 means continuous restraint
    # (chi_LT = 1, no LTB check), which reproduces spec v1.2 exactly.
    restraint_ratio: float = 0.0
    ltb_load_position: str = "shear_centre"  # or "top_flange" (destabilising, zg = +h/2)
    ltb_C1: float = 1.127  # UDL, k = 1 (NCCI SN003)
    ltb_C2: float = 0.454  # UDL, k = 1 (NCCI SN003)
    ltb_lambda0: float = 0.4  # recommended value; UK NA keeps it (6.3.2.3)
    ltb_beta: float = 0.75  # recommended value
    ltb_kc: float = 0.94  # EN 1993-1-1 Table 6.6, parabolic moment diagram (UDL)
    # Intermediate restraints (0 < restraint_ratio < 1): the critical segment does not carry the full-span UDL moment
    # shape, so the UDL factors above would be unconservative. Conservative default: uniform moment over the segment
    # at the maximum design moment (C1 = 1, kc = 1). The C2 term is kept for top-flange loading (conservative).
    # restraint_ratio = 1 (restraints at the supports only) uses ltb_C1 and ltb_kc.
    ltb_segment_C1: float = 1.0
    ltb_segment_kc: float = 1.0
    # Partial factors (UK NA)
    gamma_M0: float = 1.0
    gamma_M1: float = 1.0
    # Stations along the span for the bending-shear interaction (spec 6)
    n_stations: int = 101
    # Feasible iff every utilisation <= 1 + tol (spec 6)
    tol: float = 1e-9

    def __post_init__(self):
        if self.deflection_load not in ("variable", "total"):
            raise ValueError("deflection_load must be 'variable' or 'total'")
        if self.class4_treatment != "infeasible":
            raise NotImplementedError("only class4_treatment='infeasible' is implemented (spec 6)")
        if self.support != "fork":
            raise NotImplementedError("only fork supports are modelled (spec 6)")
        if self.restraint_ratio < 0 or self.restraint_ratio > 1:
            raise ValueError("restraint_ratio must be in [0, 1] (Lcr / L)")
        if self.ltb_load_position not in ("shear_centre", "top_flange"):
            raise ValueError("ltb_load_position must be 'shear_centre' or 'top_flange'")
        if not (self.n_stations >= 3 and self.n_stations % 2 == 1):
            raise ValueError("n_stations must be odd and >= 3 so that midspan is a station")
        for name in ("gamma_G", "gamma_Q", "deflection_ratio", "gamma_M0", "gamma_M1", "shear_eta"):
            if not getattr(self, name) > 0:
                raise ValueError(f"{name} must be positive")
        if not (0.0 <= self.variable_share <= 1.0):
            raise ValueError("variable_share must be in [0, 1]")
        if self.stiff_bearing_ss < 0 or self.bearing_c < 0:
            raise ValueError("ss and c must be >= 0")

    def as_dict(self):
        return asdict(self)
