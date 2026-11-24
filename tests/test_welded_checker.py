import numpy as np
import pytest

from ub_rl.context import Context
from ub_rl.welded_checker import WeldedChecker
from ub_rl.welded_sections import Design


def context(depth_cap=None, restraint_ratio=0.0, deflection_rule="var360"):
    return Context(span=9.0, width=6.0, dead=3.675, live=3.0,
                   depth_cap=depth_cap, restraint_ratio=restraint_ratio,
                   deflection_rule=deflection_rule)


def test_partial_status_resistances_and_unavailable_utilisations():
    checker = WeldedChecker()
    result = checker.check(context(), Design(610, 200, 10, 10))
    assert result["complete"] is False
    assert result["feasible"] is None
    assert result["passes_p14a_checks"] == {
        "geometry_valid": True, "class_ok": True, "depth_ok": True
    }
    assert result["Mc_Rd_Nmm"] > 0
    assert result["u_bending"] == "unavailable: steel density not yet recorded"
    assert result["u_deflection"] == "unavailable: steel density not yet recorded"
    assert result["p14b_fields"] == "unavailable"


def test_depth_cap_is_separate_from_geometry_and_class():
    checker = WeldedChecker()
    result = checker.check(context(depth_cap=600), Design(610, 200, 10, 10))
    assert result["geometry_valid"] is True
    assert result["class_ok"] is True
    assert result["depth_ok"] is False
    assert result["feasible"] is None


def test_invalid_geometry_and_off_grid_are_not_rounded():
    checker = WeldedChecker()
    bad_ratio = checker.check(context(), Design(620, 200, 10, 10))
    off_grid = checker.check(context(), Design(611, 200, 10, 10))
    assert bad_ratio["geometry_valid"] is False
    assert off_grid["geometry_valid"] is False
    assert checker.checker_calls == 2


def test_unique_design_call_cache_and_counters():
    checker = WeldedChecker()
    ctx = context()
    d = Design(610, 200, 10, 10)
    checker.check(ctx, d)
    assert checker.checker_calls == 1
    assert checker.cache_hits == 0
    assert checker.continuous_evaluations == 0
    checker.check(ctx, d)
    assert checker.checker_calls == 1
    assert checker.cache_hits == 1
    assert checker.continuous_evaluations == 0
    assert checker.wall_clock_seconds >= 0


def test_evaluate_context_returns_arrays_and_counts_each_unique_design():
    checker = WeldedChecker()
    rows = checker.evaluate_context(context(), [Design(610, 200, 10, 10),
                                                 Design(630, 200, 10, 10)])
    assert isinstance(rows, dict)
    assert all(isinstance(v, np.ndarray) for k, v in rows.items() if k != "passes_p14a_checks")
    assert isinstance(rows["passes_p14a_checks"]["depth_ok"], np.ndarray)
    assert rows["complete"].tolist() == [False, False]
    assert rows["feasible"].tolist() == [None, None]
    assert checker.checker_calls == 2


def test_cache_is_context_specific():
    checker = WeldedChecker()
    d = Design(610, 200, 10, 10)
    checker.check(context(), d)
    checker.check(context(depth_cap=600), d)
    assert checker.checker_calls == 2


def test_cache_key_includes_restraint_ratio():
    checker = WeldedChecker()
    d = Design(610, 200, 10, 10)
    checker.check(context(restraint_ratio=0.0), d)
    checker.check(context(restraint_ratio=0.5), d)
    assert checker.checker_calls == 2


def test_cache_key_includes_deflection_rule():
    checker = WeldedChecker()
    d = Design(610, 200, 10, 10)
    checker.check(context(deflection_rule="var360"), d)
    checker.check(context(deflection_rule="var200"), d)
    assert checker.checker_calls == 2


def test_feasibility_search_guards_raise():
    checker = WeldedChecker()
    with pytest.raises(NotImplementedError):
        checker.lightest_feasible_context(context())
    with pytest.raises(NotImplementedError):
        checker.lightest_feasible(9.0, 56.7)
