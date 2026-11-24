"""P14a partial checker; deliberately does not declare full feasibility."""
from copy import deepcopy
from time import perf_counter

import numpy as np

from .config import CheckerConfig
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
            "passes_p14a_checks": {"geometry_valid": False, "class_ok": None, "depth_ok": depth_ok},
            "geometry_valid": False,
            "class_ok": None,
            "depth_ok": depth_ok,
            "section_properties": None,
            "Mc_Rd_Nmm": None,
            "u_bending": "unavailable: steel density not yet recorded",
            "u_deflection": "unavailable: steel density not yet recorded",
            "p14b_fields": "unavailable",
        }

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
                row = {
                    "design": d,
                    "complete": False,
                    "feasible": None,
                    "passes_p14a_checks": {
                        "geometry_valid": True,
                        "class_ok": class_ok,
                        "depth_ok": depth_ok,
                    },
                    "geometry_valid": True,
                    "class_ok": class_ok,
                    "depth_ok": depth_ok,
                    "section_properties": props,
                    "Mc_Rd_Nmm": props.mc_rd if class_ok else None,
                    "u_bending": "unavailable: steel density not yet recorded",
                    "u_deflection": "unavailable: steel density not yet recorded",
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
                "passes_p14a_checks": {k: np.asarray([], dtype=object)
                                        for k in ("geometry_valid", "class_ok", "depth_ok")},
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
