"""P14a partial checker; deliberately does not declare full feasibility."""
from copy import deepcopy
from math import sqrt
from time import perf_counter

import numpy as np

from .config import CheckerConfig, E_STEEL, G_ACC
from .context import DEFLECTION_RULES
from .welded_sections import coerce_design, geometry_valid, section_properties


class WeldedChecker:
    """Compute P14a properties/check outcomes with a per-instance result cache."""

    def __init__(self, config=None):
        self.config = config or CheckerConfig()
        self._cache = {}
        self.checker_calls = 0
        self.cache_hits = 0
        self.continuous_evaluations = 0
        self.wall_clock_seconds = 0.0

    @staticmethod
    def _context_key(ctx):
        return tuple(getattr(ctx, name, None) for name in
                     ("span", "width", "dead", "live", "restraint_ratio", "deflection_rule", "depth_cap"))

    @staticmethod
    def _depth_ok(ctx, design):
        if design is None:
            return None
        cap = getattr(ctx, "depth_cap", None)
        return cap is None or design.h <= cap

    def _invalid_result(self, design, ctx):
        parsed = None
        try:
            parsed = coerce_design(design)
        except ValueError:
            pass
        depth_ok = self._depth_ok(ctx, parsed)
        return {
            "design": parsed,
            "complete": False,
            "feasible": None,
            "geometry_valid": False,
            "class_ok": None,
            "depth_ok": depth_ok,
            "section_properties": None,
            "mass_per_m_kg_m": None,
            "self_weight_kN_m": None,
            "w_Ed_kN_m": None,
            "M_Ed_kNm": None,
            "Mc_Rd_Nmm": None,
            "Av_mm2": None, "V_pl_Rd_N": None, "V_Ed_N": None, "u_shear": None,
            "u_bending": None,
            "deflection_mm": None,
            "deflection_limit_mm": None,
            "u_deflection": None,
            "passes_p14a_checks": {"geometry_valid": False, "class_ok": None,
                                    "depth_ok": depth_ok, "bending_ok": None,
                                    "deflection_ok": None, "shear_ok": None},
            "p14b_fields": "unavailable",
        }

    def _p14a2_values(self, ctx, props):
        cfg = self.config
        w, phi = ctx.factored_udl(cfg.gamma_G, cfg.gamma_Q)
        g = (props.mass_per_m * G_ACC / 1000.0
             if cfg.self_weight else 0.0)
        w_ed = w + cfg.gamma_G * g
        m_ed = w_ed * ctx.span ** 2 / 8.0
        u_bending = m_ed / (props.mc_rd / 1e6)
        av = cfg.shear_eta * props.hw * props.design.tw
        v_pl_rd = av * props.fy / (sqrt(3.0) * cfg.gamma_M0)
        v_ed = w_ed * ctx.span / 2.0 * 1000.0
        u_shear = v_ed / v_pl_rd

        mode, ratio = DEFLECTION_RULES[ctx.deflection_rule]
        q_k = phi * w / cfg.gamma_Q
        q = (q_k if mode == "variable"
             else q_k + (1.0 - phi) * w / cfg.gamma_G + g)
        span_mm = ctx.span * 1000.0
        delta = 5.0 * q * span_mm ** 4 / (384.0 * E_STEEL * props.iy)
        limit = span_mm / ratio
        return {"mass_per_m_kg_m": props.mass_per_m, "self_weight_kN_m": g,
                "w_Ed_kN_m": w_ed, "M_Ed_kNm": m_ed,
                "u_bending": u_bending, "Av_mm2": av, "V_pl_Rd_N": v_pl_rd,
                "V_Ed_N": v_ed, "u_shear": u_shear, "deflection_mm": delta,
                "deflection_limit_mm": limit, "u_deflection": delta / limit}

    def check(self, ctx, design):
        """Return one partial-result dict; never assert full structural feasibility."""
        result = self.evaluate_context(ctx, [design])
        scalar = {}
        for key, value in result.items():
            if isinstance(value, np.ndarray):
                scalar[key] = value[0].item() if value.ndim == 1 and value.dtype != object else value[0]
            elif key == "passes_p14a_checks":
                scalar[key] = {name: np.asarray(arr[0]).item() for name, arr in value.items()}
            else:
                scalar[key] = value
        return scalar

    def evaluate_context(self, ctx, designs=None):
        """Return one dictionary of NumPy arrays for P14a results over supplied designs."""
        if designs is None:
            raise ValueError("P14a requires explicit candidate designs; grid-wide feasibility is unavailable")
        if isinstance(designs, (tuple, list)) and len(designs) == 4 and all(
                isinstance(v, (int, np.integer)) and not isinstance(v, (bool, np.bool_)) for v in designs):
            designs = [designs]
        started = perf_counter()
        rows = []
        for raw in designs:
            try:
                d = coerce_design(raw)
                design_key = tuple(d)
            except ValueError:
                d = None
                design_key = repr(raw)
            key = (design_key, self._context_key(ctx))
            if key in self._cache:
                self.cache_hits += 1
                rows.append(deepcopy(self._cache[key]))
                continue
            self.checker_calls += 1
            row = self._invalid_result(raw, ctx)
            if d is not None and geometry_valid(d):
                props = section_properties(d, self.config)
                depth_ok = self._depth_ok(ctx, d)
                class_ok = props.section_class <= 3
                values = self._p14a2_values(ctx, props) if class_ok else {
                    "mass_per_m_kg_m": None, "self_weight_kN_m": None,
                    "w_Ed_kN_m": None, "M_Ed_kNm": None, "u_bending": None,
                    "deflection_mm": None, "deflection_limit_mm": None,
                    "u_deflection": None,
                    "Av_mm2": None, "V_pl_Rd_N": None, "V_Ed_N": None, "u_shear": None,
                }
                row = {
                    "design": d,
                    "complete": False,
                    "feasible": None,
                    "passes_p14a_checks": {
                        "geometry_valid": True,
                        "class_ok": class_ok,
                        "depth_ok": depth_ok,
                        "bending_ok": (values["u_bending"] <= 1.0 + self.config.tol
                                       if class_ok else None),
                        "deflection_ok": (values["u_deflection"] <= 1.0 + self.config.tol
                                          if class_ok else None),
                        "shear_ok": (values["u_shear"] <= 1.0 + self.config.tol
                                     if class_ok else None),
                    },
                    "geometry_valid": True,
                    "class_ok": class_ok,
                    "depth_ok": depth_ok,
                    "section_properties": props,
                    "Mc_Rd_Nmm": props.mc_rd if class_ok else None,
                    **values,
                    "p14b_fields": "unavailable",
                }
            self._cache[key] = deepcopy(row)
            rows.append(row)
        self.wall_clock_seconds += perf_counter() - started
        return self._arrays(rows)

    def _arrays(self, rows):
        if not rows:
            return {
                "design": np.asarray([], dtype=object),
                "complete": np.asarray([], dtype=bool),
                "feasible": np.asarray([], dtype=object),
                "geometry_valid": np.asarray([], dtype=object),
                "class_ok": np.asarray([], dtype=object),
                "depth_ok": np.asarray([], dtype=object),
                "section_properties": np.asarray([], dtype=object),
                "mass_per_m_kg_m": np.asarray([], dtype=object),
                "self_weight_kN_m": np.asarray([], dtype=object),
                "w_Ed_kN_m": np.asarray([], dtype=object),
                "M_Ed_kNm": np.asarray([], dtype=object),
                "Mc_Rd_Nmm": np.asarray([], dtype=object),
                "Av_mm2": np.asarray([], dtype=object),
                "V_pl_Rd_N": np.asarray([], dtype=object),
                "V_Ed_N": np.asarray([], dtype=object),
                "u_shear": np.asarray([], dtype=object),
                "u_bending": np.asarray([], dtype=object),
                "deflection_mm": np.asarray([], dtype=object),
                "deflection_limit_mm": np.asarray([], dtype=object),
                "u_deflection": np.asarray([], dtype=object),
                "p14b_fields": np.asarray([], dtype=object),
                "passes_p14a_checks": {k: np.asarray([], dtype=object)
                                        for k in ("geometry_valid", "class_ok", "depth_ok",
                                                  "bending_ok", "deflection_ok", "shear_ok")},
            }
        result = {}
        keys = rows[0].keys()
        for key in keys:
            if key == "passes_p14a_checks":
                result[key] = {name: np.asarray([r[key][name] for r in rows], dtype=object)
                               for name in rows[0][key]}
            else:
                result[key] = np.asarray([r[key] for r in rows], dtype=object)
        return result

    def lightest_feasible_context(self, ctx):
        raise NotImplementedError("P14a is partial; feasibility search requires complete P14b checks")

    def lightest_feasible(self, *args, **kwargs):
        raise NotImplementedError("P14a is partial; feasibility search requires complete P14b checks")
