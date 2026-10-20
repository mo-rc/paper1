"""Design context: the seven parameters the policy must generalise across (proposal section 5, amendment A1).

span, tributary width, dead load, live load, restraint ratio, deflection rule, depth cap. The sampling ranges and the
train/validation/test split are fixed at Gate 3, not here."""
from dataclasses import dataclass
from typing import Optional

# Restraint ratios allowed in contexts: 0 (continuous), (0, RESTRAINT_MAX_INTERIOR] or exactly 1. The LTB model is not
# monotone between about 0.5 and 1: Mcr falls to ratio 0.99 and then rises at 1.0 because the UDL factors (C1 = 1.127,
# kc = 0.94) apply only at ratio 1. Contexts in (0.5, 1) are rejected so that a policy cannot learn that artefact.
RESTRAINT_MAX_INTERIOR = 0.5

# rule name -> (deflection load, span ratio). var360 is the primary rule (spec section 3).
DEFLECTION_RULES = {
    "var360": ("variable", 360.0),
    "var200": ("variable", 200.0),
    "tot250": ("total", 250.0),
}


@dataclass(frozen=True)
class Context:
    span: float  # m
    width: float  # m, tributary width
    dead: float  # kN/m2, superimposed dead load (self-weight is added by the checker)
    live: float  # kN/m2
    restraint_ratio: float = 0.0  # Lcr / L; 0 = continuous restraint
    deflection_rule: str = "var360"
    depth_cap: Optional[float] = None  # mm, maximum section depth h; None = no cap

    def __post_init__(self):
        for name in ("span", "width"):
            if not getattr(self, name) > 0:
                raise ValueError(f"{name} must be positive")
        if self.dead < 0 or self.live < 0 or self.dead + self.live <= 0:
            raise ValueError("dead and live loads must be >= 0 and not both zero")
        r = self.restraint_ratio
        if not (r == 0.0 or 0.0 < r <= RESTRAINT_MAX_INTERIOR or r == 1.0):
            raise ValueError(f"restraint_ratio must be 0, in (0, {RESTRAINT_MAX_INTERIOR}] or 1 (LTB model artefact in between)")
        if self.deflection_rule not in DEFLECTION_RULES:
            raise ValueError(f"deflection_rule must be one of {sorted(DEFLECTION_RULES)}")
        if self.depth_cap is not None and not self.depth_cap > 0:
            raise ValueError("depth_cap must be positive or None")

    def factored_udl(self, gamma_G=1.35, gamma_Q=1.5):
        """Factored superimposed UDL w (kN/m) and its variable share phi."""
        gd, ql = gamma_G * self.dead, gamma_Q * self.live
        return (gd + ql) * self.width, ql / (gd + ql)
