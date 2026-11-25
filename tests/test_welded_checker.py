import numpy as np
import pytest

from ub_rl.context import Context
from ub_rl.welded_checker import WeldedChecker
from ub_rl.welded_sections import Design


def context(depth_cap=None, restraint_ratio=0.0, deflection_rule="var360"):
    return Context(span=9.0, width=6.0, dead=3.675, live=3.0,
                   depth_cap=depth_cap, restraint_ratio=restraint_ratio,
                   deflection_rule=deflection_rule)


def test_partial_status_resistances_and_computed_utilisations():
    checker = WeldedChecker()
    result = checker.check(context(), Design(610, 200, 10, 10))
    assert result["complete"] is False
    assert result["feasible"] is None
    assert result["passes_p14a_checks"] == {
        "geometry_valid": True, "class_ok": True, "depth_ok": True,
        "bending_ok": result["u_bending"] <= 1.0 + checker.config.tol,
        "deflection_ok": result["u_deflection"] <= 1.0 + checker.config.tol,
    }
    assert result["Mc_Rd_Nmm"] > 0
    assert result["mass_per_m_kg_m"] == pytest.approx(((2 * 200 * 10 + 590 * 10) * 7850) / 1e6)
    assert result["u_bending"] >= 0
    assert result["u_deflection"] >= 0
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


def test_hand_calculated_mass_self_weight_and_bending_case():
    # Design area A=2*200*10 + 580*10 = 9,800 mm2.
    # Mass=9,800*7,850/1e6=76.93 kg/m; g=76.93*9.80665/1000=0.754425585 kN/m.
    # w=56.7675 kN/m; wEd=56.7675+1.35*0.754425585=57.78597453975 kN/m.
    # MEd=57.78597453975*9^2/8=585.08299221496875 kNm.
    checker = WeldedChecker()
    result = checker.check(context(), Design(600, 200, 10, 10))
    assert result["mass_per_m_kg_m"] == pytest.approx(76.93)
    assert result["self_weight_kN_m"] == pytest.approx(0.754425585)
    assert result["w_Ed_kN_m"] == pytest.approx(57.78597453975)
    assert result["M_Ed_kNm"] == pytest.approx(585.08299221496875)
    # This design is Class 3: Mc=Wel*fy=1,702,422.222...*355 Nmm; u=585.082992.../(Mc/1e6).
    expected_u = 585.08299221496875 / (1_702_422.2222222 * 355 / 1e6)
    assert result["u_bending"] == pytest.approx(expected_u)


@pytest.mark.parametrize("rule,ratio,uses_self_weight", [
    ("var360", 360.0, False), ("var200", 200.0, False), ("tot250", 250.0, True),
])
def test_each_context_deflection_rule(rule, ratio, uses_self_weight):
    # Given: Qk=18, Gk=22.05 kN/m, g=0.754425585 kN/m,
    # Iy=510,726,666.67 mm4, E=210,000 N/mm2, L=9,000 mm.
    # q is 18 for var360/var200 and 18+22.05+0.754425585 for tot250.
    # delta=5*q*9000^4/(384*210000*510726666.67); utilization=delta/(9000/ratio).
    checker = WeldedChecker()
    result = checker.check(context(deflection_rule=rule), Design(600, 200, 10, 10))
    q = 18.0 + (22.05 + 0.754425585 if uses_self_weight else 0.0)
    expected_delta = 5.0 * q * 9000.0 ** 4 / (384.0 * 210000.0 * 510726666.67)
    assert result["deflection_limit_mm"] == pytest.approx(9000.0 / ratio)
    assert result["deflection_mm"] == pytest.approx(expected_delta, rel=1e-9)
    assert result["u_deflection"] == pytest.approx(expected_delta / (9000.0 / ratio), rel=1e-9)


def test_density_changes_bending_and_total_load_deflection_only(monkeypatch):
    ctx = context()
    design = Design(600, 200, 10, 10)
    import ub_rl.welded_sections as sections
    original = sections.STEEL_DENSITY_KG_M3
    rules = ("var360", "var200", "tot250")
    baseline = {rule: WeldedChecker().check(context(deflection_rule=rule), design)
                for rule in rules}
    monkeypatch.setattr(sections, "STEEL_DENSITY_KG_M3", original * 1.1)
    heavier = {rule: WeldedChecker().check(context(deflection_rule=rule), design)
               for rule in rules}
    for rule in rules:
        assert heavier[rule]["M_Ed_kNm"] > baseline[rule]["M_Ed_kNm"]
    for rule in ("var360", "var200"):
        assert heavier[rule]["deflection_mm"] == pytest.approx(baseline[rule]["deflection_mm"])
    assert heavier["tot250"]["deflection_mm"] > baseline["tot250"]["deflection_mm"]


def test_moment_unit_conversion_is_nmm_to_knm():
    # Given W_el=1,702,422.2222 mm3, fy=355 N/mm2, so Mc=604,359,888.881 Nmm.
    # Dividing by 1e6 converts Nmm to kNm; u_bending=MEd[kNm]/Mc[kNm].
    result = WeldedChecker().check(context(), Design(600, 200, 10, 10))
    expected_mc = 1_702_422.2222 * 355
    assert result["Mc_Rd_Nmm"] == pytest.approx(expected_mc, rel=1e-9)
    assert result["u_bending"] == pytest.approx(
        result["M_Ed_kNm"] / (expected_mc / 1e6), rel=1e-9)


def test_config_can_disable_self_weight():
    from dataclasses import replace
    from ub_rl.config import CheckerConfig

    # With self-weight disabled, g=0 and wEd remains the context's factored UDL.
    config = replace(CheckerConfig(), self_weight=False)
    result = WeldedChecker(config).check(context(deflection_rule="tot250"), Design(600, 200, 10, 10))
    w, _ = context().factored_udl(config.gamma_G, config.gamma_Q)
    assert result["mass_per_m_kg_m"] == pytest.approx(76.93)
    assert result["self_weight_kN_m"] == 0.0
    assert result["w_Ed_kN_m"] == pytest.approx(w)


def test_empty_batch_status_keys_match_nonempty_rows():
    rows = WeldedChecker().evaluate_context(context(), [])
    assert set(rows["passes_p14a_checks"]) == {
        "geometry_valid", "class_ok", "depth_ok", "bending_ok", "deflection_ok"
    }


def test_batch_valid_invalid_class4_rows_align():
    batch = WeldedChecker().evaluate_context(context(), [
        Design(600, 200, 10, 10), Design(620, 200, 10, 10), Design(900, 450, 6, 8)])
    assert batch["mass_per_m_kg_m"].tolist()[0] is not None
    assert batch["mass_per_m_kg_m"].tolist()[1:] == [None, None]
    assert batch["passes_p14a_checks"]["bending_ok"].tolist()[0] in (True, False)
    assert batch["passes_p14a_checks"]["bending_ok"].tolist()[1:] == [None, None]
    assert batch["complete"].tolist() == [False] * 3
    assert batch["feasible"].tolist() == [None] * 3


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
