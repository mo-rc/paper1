from dataclasses import replace

import numpy as np
import pytest

from ub_rl.checker import Checker
from ub_rl.config import CheckerConfig
from ub_rl.context import Context, DEFLECTION_RULES

REF = Context(span=9.0, width=6.0, dead=3.675, live=3.0)


def test_reference_context_arithmetic():
    w, phi = REF.factored_udl()
    assert w == pytest.approx(56.7675)
    assert phi == pytest.approx(27.0 / 56.7675)


def test_reference_context_reproduces_two_parameter_evaluation(C):
    K = Checker(C)
    a = K.evaluate_context(REF)
    b = K.evaluate(9.0, 56.7675)
    assert np.allclose(a["U"], b["U"], rtol=1e-12, atol=0) and np.array_equal(a["feasible"], b["feasible"])
    assert C.names[K.lightest_feasible_context(REF)] == "457x191x74"


def test_dead_live_split_changes_only_variable_dependent_checks(C):
    K = Checker(C)
    a = K.evaluate_context(Context(9.0, 6.0, 3.675, 3.0))
    b = K.evaluate_context(Context(9.0, 6.0, 1.0, 5.0))  # different split
    assert not np.allclose(a["u_deflection"], b["u_deflection"])


@pytest.mark.parametrize("rule", sorted(DEFLECTION_RULES))
def test_deflection_rules_match_direct_config(C, rule):
    mode, ratio = DEFLECTION_RULES[rule]
    ctx = Context(9.0, 6.0, 3.675, 3.0, deflection_rule=rule)
    a = Checker(C).evaluate_context(ctx)["u_deflection"]
    b = Checker(C, replace(CheckerConfig(), deflection_load=mode, deflection_ratio=ratio)).evaluate(9.0, 56.7675)["u_deflection"]
    assert np.allclose(a, b, rtol=1e-12, atol=0)


def test_restraint_passes_through(C):
    K = Checker(C)
    a = K.evaluate_context(Context(9.0, 6.0, 3.675, 3.0, restraint_ratio=0.5))
    b = Checker(C, replace(CheckerConfig(), restraint_ratio=0.5)).evaluate(9.0, 56.7675)
    assert np.allclose(a["u_ltb"], b["u_ltb"], rtol=1e-12, atol=0) and K.cfg.restraint_ratio == 0.0


def test_depth_cap_excludes_deep_sections_and_can_force_abstention(C):
    K = Checker(C)
    capped = K.evaluate_context(replace(REF, depth_cap=500.0))
    assert not np.any(capped["feasible"] & (C.cols["h"] > 500.0))
    assert np.all(capped["feasible"] <= capped["feasible_code"])
    i = K.lightest_feasible_context(replace(REF, depth_cap=500.0))
    assert i is not None and C.cols["h"][i] <= 500.0
    assert K.lightest_feasible_context(replace(REF, depth_cap=150.0)) is None


def test_with_config_does_not_mutate_original(C):
    K = Checker(C)
    K.with_config(restraint_ratio=1.0)
    assert K.cfg.restraint_ratio == 0.0


@pytest.mark.parametrize("kw", [dict(span=0), dict(width=-1), dict(dead=-1), dict(live=-1), dict(restraint_ratio=2),
                                dict(deflection_rule="x"), dict(depth_cap=0)])
def test_context_validation(kw):
    base = dict(span=9.0, width=6.0, dead=3.675, live=3.0)
    base.update(kw)
    with pytest.raises(ValueError):
        Context(**base)
