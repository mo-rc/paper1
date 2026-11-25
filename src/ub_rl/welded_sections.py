"""P14a welded-section grid and load-independent section calculations.

Geometry inputs/outputs use integer mm. Equations and grid bounds follow
docs/a4_proposal.md:10,18-19,23. Steel and classification rules follow
docs/spec.md:53-54,64,78-80. This module does not determine demand feasibility.
"""
from dataclasses import dataclass
from typing import NamedTuple

import numpy as np

from .config import CheckerConfig

# PROVISIONAL convention; see docs/verification_record.md, "Steel density convention (PROVISIONAL)".
STEEL_DENSITY_KG_M3 = 7850.0


# Bounds and increments: docs/a4_proposal.md:10.
H_VALUES = range(300, 901, 10)
B_VALUES = range(150, 451, 10)
TW_VALUES = range(6, 21)
TF_VALUES = range(8, 41)

# Classification limits are the Stage 1 code/spec limits: docs/spec.md:78-80;
# matching implementation: src/ub_rl/checker.py:99-104.
FLANGE_CLASS_LIMITS = (9.0, 10.0, 14.0)
WEB_CLASS_LIMITS = (72.0, 83.0, 124.0)


class Design(NamedTuple):
    h: int
    b: int
    tw: int
    tf: int


@dataclass(frozen=True)
class SectionProperties:
    design: Design
    area: int  # mm2
    mass_per_m: float  # kg/m, using the provisional density convention
    hw: int  # mm, clear web depth
    iy: float  # mm4, strong axis
    iz: float  # mm4, weak axis
    wel_y: float  # mm3
    wpl_y: float  # mm3
    fy: float  # N/mm2
    epsilon: float
    flange_class: int
    web_class: int
    section_class: int
    mc_rd: float  # N mm


def coerce_design(design):
    """Parse a Design, mapping, or four-value sequence without rounding."""
    if isinstance(design, Design):
        values = design
    elif isinstance(design, dict):
        try:
            values = Design(*(design[k] for k in ("h", "b", "tw", "tf")))
        except (KeyError, TypeError) as exc:
            raise ValueError("design must provide h, b, tw and tf") from exc
    else:
        try:
            values = Design(*design)
        except (TypeError, ValueError) as exc:
            raise ValueError("design must contain h, b, tw and tf") from exc
    if any(isinstance(v, (bool, np.bool_)) or not isinstance(v, (int, np.integer)) for v in values):
        raise ValueError("geometry must use canonical integer millimetres")
    return Design(*(int(v) for v in values))


def geometry_valid(design):
    """Whether a canonical grid design is in bounds and geometrically valid."""
    try:
        d = coerce_design(design)
    except ValueError:
        return False
    if d.h not in H_VALUES or d.b not in B_VALUES or d.tw not in TW_VALUES or d.tf not in TF_VALUES:
        return False
    return d.h >= d.b and d.h > 2 * d.tf and d.b > d.tw and 10 * d.h < 31 * d.b


def grid_count():
    """Count designs admitted by the A4 integer grid (710,325)."""
    return sum(1 for h in H_VALUES for b in B_VALUES for tw in TW_VALUES for tf in TF_VALUES
               if h >= b and h > 2 * tf and b > tw and 10 * h < 31 * b)


def make_grid():
    """Return designs ordered by integer area, then h,b,tw,tf ascending."""
    designs = [Design(h, b, tw, tf)
               for h in H_VALUES for b in B_VALUES for tw in TW_VALUES for tf in TF_VALUES
               if h >= b and h > 2 * tf and b > tw and 10 * h < 31 * b]
    return sorted(designs, key=lambda d: (2 * d.b * d.tf + (d.h - 2 * d.tf) * d.tw,
                                          d.h, d.b, d.tw, d.tf))


def _class(ratio, limits):
    return next((idx for idx, limit in enumerate(limits, start=1) if ratio <= limit), 4)


def classify_section(cf_tf, cw_tw, epsilon):
    """Return flange, web and governing classes from normalized element ratios."""
    return (_class(cf_tf / epsilon, FLANGE_CLASS_LIMITS),
            _class(cw_tw / epsilon, WEB_CLASS_LIMITS),
            max(_class(cf_tf / epsilon, FLANGE_CLASS_LIMITS),
                _class(cw_tw / epsilon, WEB_CLASS_LIMITS)))


def yield_strength(max_element_thickness):
    """S355 fy bands by max element thickness, sourced from docs/spec.md:53-54."""
    t = float(max_element_thickness)
    if not np.isfinite(t) or t <= 0 or t > 80:
        raise ValueError("maximum element thickness must be in (0, 80] mm")
    return 355.0 if t <= 16 else 345.0 if t <= 40 else 335.0 if t <= 63 else 325.0


def section_properties(design, config=None):
    """Return P14a load-independent properties for one valid grid design.

    Properties follow docs/a4_proposal.md:18-19. The bending resistance factor
    comes from CheckerConfig (src/ub_rl/config.py:13-52), not a copied value.
    """
    d = coerce_design(design)
    if not geometry_valid(d):
        raise ValueError("invalid or off-grid welded geometry")
    cfg = config or CheckerConfig()
    h, b, tw, tf = d
    hw = h - 2 * tf
    area = 2 * b * tf + hw * tw
    mass_per_m = area * STEEL_DENSITY_KG_M3 / 1e6
    iy = 2 * (b * tf ** 3 / 12.0 + b * tf * ((h - tf) / 2.0) ** 2) + tw * hw ** 3 / 12.0
    iz = 2 * tf * b ** 3 / 12.0 + hw * tw ** 3 / 12.0
    wel_y = iy / (h / 2.0)
    # Symmetric-section plastic neutral axis is at mid-depth; A4 design equation.
    wpl_y = b * tf * (h - tf) + tw * hw ** 2 / 4.0

    max_t = max(tf, tw)
    fy = yield_strength(max_t)
    epsilon = float(np.sqrt(235.0 / fy))
    flange_ratio = ((b - tw) / 2.0) / tf
    web_ratio = hw / tw
    flange_class, web_class, section_class = classify_section(flange_ratio, web_ratio, epsilon)

    mc_rd = (wpl_y if section_class <= 2 else wel_y) * fy / cfg.gamma_M0
    return SectionProperties(d, area, mass_per_m, hw, iy, iz, wel_y, wpl_y, fy, epsilon,
                             flange_class, web_class, section_class, mc_rd)
